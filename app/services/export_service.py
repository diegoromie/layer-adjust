import ezdxf
import os
import logging
from pathlib import Path
from typing import List
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

logger = logging.getLogger(__name__)

class ExportService:
    
    def merge_dxfs_to_single_file(self, file_paths: List[Path], output_path: Path):
        """
        Cria um único arquivo DXF onde cada arquivo da lista se torna um Layout (Paper Space).
        """
        if not file_paths:
            return

        # Cria o documento mestre
        doc_master = ezdxf.new()
        
        # Ordena arquivos (opcional, mas bom para garantir ordem FL1, FL2...)
        # Assumindo que o nome do arquivo ajude na ordenação, caso contrário usa a ordem da lista
        file_paths.sort(key=lambda p: p.name)

        for i, file_path in enumerate(file_paths):
            try:
                # Carrega o arquivo individual do disco (apenas este arquivo na RAM)
                doc_source = ezdxf.readfile(str(file_path))
                msp_source = doc_source.modelspace()
                
                # Define nome do Layout (Ex: FL 01, FL 02...)
                layout_name = f"FL {i+1:02d}"
                
                # Cria o layout no mestre
                # Nota: DXF R2000+ suporta múltiplos layouts.
                if layout_name in doc_master.layouts:
                    layout_name = f"FL {i+1:02d}_{file_path.stem}" # Evita duplicatas
                
                layout_target = doc_master.layouts.new(layout_name)

                # --- Cópia de Recursos (Layers, Linetypes, Styles) ---
                # É crucial copiar os recursos antes das entidades para não dar erro de referência
                self._copy_resources(doc_source, doc_master)

                # --- Cópia de Entidades ---
                # Movemos tudo do ModelSpace do arquivo original para o PaperSpace do layout novo
                for entity in msp_source:
                    try:
                        # O método .copy() cria uma entidade desconectada (virtual)
                        new_entity = entity.copy()
                        layout_target.add_entity(new_entity)
                    except Exception as e:
                        logger.warning(f"Falha ao copiar entidade {entity.dxftype()} de {file_path.name}: {e}")

                logger.info(f"Arquivo {file_path.name} importado para o layout {layout_name}")
                
                # Limpa doc_source da memória explicitamente (boa prática em loops pesados)
                del doc_source 

            except Exception as e:
                logger.error(f"Erro ao mesclar arquivo {file_path.name}: {e}")

        # Salva o mestre no disco
        doc_master.saveas(str(output_path))


    def export_pdf_from_dxf(self, dxf_path: Path, pdf_output_path: Path):
        """
        Converte um DXF para PDF usando Matplotlib.
        Se for MULTIPLOS_ARQUIVOS, gera um PDF por DXF.
        Se for ARQUIVO_UNICO, o ideal seria usar uma lib de merge de PDF depois, 
        mas aqui vamos gerar o PDF do ModelSpace.
        """
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()

            # Configuração de Renderização
            ctx = RenderContext(doc)
            # Melhora a visualização (fundo branco, cores escuras viram preto)
            ctx.set_current_layout(msp)
            
            fig = plt.figure()
            ax = fig.add_axes([0, 0, 1, 1])
            
            out = MatplotlibBackend(ax)
            
            # O Frontend orquestra o desenho
            Frontend(ctx, out).draw_layout(msp, finalize=True)
            
            # Salva PDF
            fig.savefig(str(pdf_output_path), dpi=300)
            plt.close(fig) # Libera memória do Matplotlib
            
        except Exception as e:
            logger.error(f"Erro ao renderizar PDF {dxf_path.name}: {e}")
            raise RuntimeError(f"Falha na exportação PDF: {e}")

    def _copy_resources(self, source, target):
        """Copia Layers, Linetypes e TextStyles do source para o target"""
        
        # Copia Layers
        for layer in source.layers:
            if layer.dxf.name not in target.layers:
                try:
                    target.layers.add(
                        name=layer.dxf.name,
                        color=layer.dxf.color,
                        linetype=layer.dxf.linetype
                    )
                    # Define espessura
                    target.layers.get(layer.dxf.name).dxf.lineweight = layer.dxf.lineweight
                except:
                    pass

        # Copia Linetypes (Simples)
        for ltype in source.linetypes:
            if ltype.dxf.name not in target.linetypes:
                try:
                    # Copiar linetypes complexos é difícil, tentamos copiar o padrão
                    # Se falhar, o ezdxf usa Continuous
                    pattern = ltype.dxf.pattern if hasattr(ltype.dxf, 'pattern') else None
                    if pattern:
                        target.linetypes.add(ltype.dxf.name, pattern)
                except:
                    pass
        
        # Copia Styles (Fontes)
        for style in source.styles:
             if style.dxf.name not in target.styles:
                try:
                    target.styles.add(style.dxf.name, font=style.dxf.font)
                except:
                    pass