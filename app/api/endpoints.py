import json
import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from app.models.schemas import ProcessingOptions, OutputMode, OutputFormat
from app.services.layer_mapper import LayerMapperService
from app.services.dxf_processor import DXFProcessorService
from app.utils.file_manager import FileManager
from app.services.export_service import ExportService

import ezdxf

router = APIRouter()

file_manager = FileManager()
layer_mapper = LayerMapperService()
dxf_processor = DXFProcessorService()
export_service = ExportService()

@router.post("/process-dxf")
async def process_dxf(
    background_tasks: BackgroundTasks,
    zip_file: UploadFile = File(...),
    excel_file: UploadFile = File(...),
    options_str: str = Form(..., alias="options")
):
    try:
        options_dict = json.loads(options_str)
        options = ProcessingOptions(**options_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro no formato das opções JSON: {str(e)}")

    temp_dir = Path(tempfile.mkdtemp())
    upload_dir = temp_dir / "uploads"
    output_dir = temp_dir / "output"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Leitura Excel
        excel_content = await excel_file.read()
        try:
            rules = layer_mapper.parse_excel_rules(excel_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Manipulação ZIP
        zip_path = file_manager.save_upload_file(zip_file, upload_dir)
        dxf_files = file_manager.extract_zip(zip_path, upload_dir)

        if not dxf_files:
            raise HTTPException(status_code=400, detail="O ZIP não contém arquivos .dxf válidos.")

        # --- TRATAMENTO DO LOGOS.DXF ---
        logos_doc = None
        # Procura por 'logos.dxf' (case insensitive)
        logos_file = next((f for f in dxf_files if f.name.lower() == 'logos.dxf'), None)

        if logos_file:
            print(f"Arquivo de logos encontrado: {logos_file.name}")
            try:
                logos_doc = ezdxf.readfile(str(logos_file))
                
                # Prepara o logo: explode tudo para evitar problemas de cópia de blocos aninhados
                # Usamos o próprio processador para limpar o logo antes de usá-lo como carimbo
                msp_logo = logos_doc.modelspace()
                dxf_processor.explode_drawing(msp_logo)
                dxf_processor.purge_blocks(logos_doc)
                
                # Remove o logos.dxf da lista de arquivos a serem processados (regras de layer)
                dxf_files.remove(logos_file)
            except Exception as e:
                print(f"Erro ao carregar logos.dxf: {e}")
                # Se falhar ao carregar o logo, continuamos sem ele (ou poderíamos lançar erro)

        # Processamento dos Arquivos
        processed_files = []
        
        for dxf_path in dxf_files:
            try:
                doc = ezdxf.readfile(str(dxf_path))
                
                # Passamos o logos_doc aqui!
                doc = dxf_processor.process_dxf(doc, rules, options, logos_doc=logos_doc)
                
                output_path = output_dir / dxf_path.name
                doc.saveas(str(output_path))
                processed_files.append(output_path)
            except Exception as e:
                print(f"Erro ao processar {dxf_path.name}: {e}")
                continue

        if not processed_files:
            raise HTTPException(status_code=500, detail="Nenhum arquivo processado com sucesso.")

        # Consolidação (Manteve igual)
        final_file_path = None
        final_filename = "resultado.zip"
        media_type = "application/zip"

        if options.modo_saida == OutputMode.ARQUIVO_UNICO and options.formato_saida == OutputFormat.DXF:
            merged_path = output_dir / "projeto_consolidado.dxf"
            export_service.merge_dxfs_to_single_file(processed_files, merged_path)
            final_file_path = merged_path
            final_filename = "projeto_consolidado.dxf"
            media_type = "application/dxf"

        elif options.formato_saida == OutputFormat.PDF:
            pdf_dir = output_dir / "pdfs"
            pdf_dir.mkdir(exist_ok=True)
            generated_pdfs = []
            for dxf_path in processed_files:
                pdf_name = dxf_path.stem + ".pdf"
                pdf_path = pdf_dir / pdf_name
                try:
                    export_service.export_pdf_from_dxf(dxf_path, pdf_path)
                    generated_pdfs.append(pdf_path)
                except Exception:
                    pass
            zip_output = file_manager.create_zip(pdf_dir, "projeto_pdfs.zip")
            final_file_path = zip_output
            final_filename = "projeto_pdfs.zip"
            media_type = "application/zip"

        else:
            zip_output = file_manager.create_zip(output_dir, "dxf_processados.zip")
            final_file_path = zip_output
            final_filename = "dxf_processados.zip"
            media_type = "application/zip"

        background_tasks.add_task(shutil.rmtree, temp_dir, ignore_errors=True)

        return FileResponse(
            path=final_file_path,
            filename=final_filename,
            media_type=media_type
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")