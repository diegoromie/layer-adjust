import ezdxf
import logging
import os
from pathlib import Path
from typing import List
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons import Importer
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
from ezdxf import options
from ezdxf.fonts import fonts
import ezdxf.bbox

logger = logging.getLogger(__name__)

class ExportService:
    
    def merge_dxfs_to_single_file(self, file_paths: List[Path], output_path: Path):
        """
        Cria um único arquivo DXF usando o Importer para garantir que Layers e Blocos não quebrem.
        """
        if not file_paths:
            return

        doc_master = ezdxf.new()
        file_paths.sort(key=lambda p: p.name)

        for i, file_path in enumerate(file_paths):
            try:
                doc_source = ezdxf.readfile(str(file_path))
                msp_source = doc_source.modelspace()
                
                # Nome do Layout
                layout_name = f"FL {i+1:02d}"
                if layout_name in doc_master.layouts:
                    layout_name = f"FL {i+1:02d}_{file_path.stem}"
                
                layout_target = doc_master.layouts.new(layout_name)

                # --- MUDANÇA PRINCIPAL: USAR IMPORTER ---
                try:
                    importer = Importer(doc_source, doc_master)
                    importer.import_tables('*') # Importa Layers, Linetypes, Styles...
                    importer.finalize()
                except Exception as e:
                    logger.warning(f"Aviso importando tabelas de {file_path.name}: {e}")

                # Copia entidades
                for entity in msp_source:
                    try:
                        new_entity = entity.copy()
                        layout_target.add_entity(new_entity)
                    except: pass
                
                del doc_source 

            except Exception as e:
                logger.error(f"Erro ao mesclar {file_path.name}: {e}")

        doc_master.saveas(str(output_path))


    def export_pdf_from_dxf(self, dxf_path: Path, pdf_output_path: Path):
        """
        Converte DXF para PDF (P/B) com ENQUADRAMENTO FORÇADO.
        Usa finalize=False e aplica limites depois do desenho.
        """
        try:
            doc = ezdxf.readfile(str(dxf_path))
            msp = doc.modelspace()

            # --- 1. CONFIGURAÇÃO DE FONTES ---
            try:
                if hasattr(fonts, 'build_system_font_cache'):
                     fonts.build_system_font_cache()
            except Exception: pass

            # --- 2. CÁLCULO DOS LIMITES (BBOX) ---
            valid_entities = []
            for e in msp:
                if e.dxf.layer.lower() != 'defpoints':
                    valid_entities.append(e)
            
            extents = ezdxf.bbox.extents(valid_entities)
            
            # Valores padrão A3
            min_x, min_y = 0, 0
            max_x, max_y = 420, 297

            if extents.has_data:
                min_x = extents.extmin.x
                min_y = extents.extmin.y
                max_x = extents.extmax.x
                max_y = extents.extmax.y
            
            width = max_x - min_x
            height = max_y - min_y
            
            print(f"DEBUG PDF: Dimensões {dxf_path.name}: {width:.2f}mm x {height:.2f}mm")

            # Converte MM para Polegadas
            figsize_inch = (width / 25.4, height / 25.4)

            # --- 3. RENDERIZAÇÃO ---
            ctx = RenderContext(doc)
            
            cfg = Configuration.defaults().with_changes(
                background_policy=BackgroundPolicy.WHITE,
                color_policy=ColorPolicy.BLACK
            )
            
            # Cria a figura com o tamanho exato
            fig = plt.figure(figsize=figsize_inch)
            
            # Eixo ocupando 100% da figura
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_facecolor('white')
            ax.set_axis_off()
            
            out = MatplotlibBackend(ax)
            
            # MUDANÇA CRÍTICA 1: finalize=False
            # Isso impede o ezdxf de recalcular o zoom automaticamente
            Frontend(ctx, out, config=cfg).draw_layout(msp, finalize=False)
            
            # MUDANÇA CRÍTICA 2: Aplicar limites DEPOIS de desenhar
            # Garante que a "câmera" do PDF mostre exatamente essa região
            ax.set_xlim(min_x, max_x)
            ax.set_ylim(min_y, max_y)
            
            # Garante que preencha tudo sem travar aspect ratio (estica se necessário imperceptivelmente)
            ax.set_aspect('auto')
            
            fig.savefig(str(pdf_output_path), dpi=300)
            plt.close(fig)
            
        except Exception as e:
            logger.error(f"Erro PDF {dxf_path.name}: {e}")
            raise RuntimeError(f"Falha exportação PDF: {e}")

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