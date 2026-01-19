import ezdxf
import logging
from typing import Dict, Set, Optional
import ezdxf.revcloud
from app.services.layer_mapper import LayerRule

logger = logging.getLogger(__name__)

class DXFProcessorService:
    
    def process_dxf(self, doc, rules: Dict[str, LayerRule], options, logos_doc: Optional[ezdxf.document.Drawing] = None):
        """
        Orquestra a correção do arquivo DXF.
        Agora aceita um documento opcional 'logos_doc' para inserir o carimbo.
        """
        msp = doc.modelspace()

        # 1. Limpeza Inicial
        self.explode_all_inserts(msp)
        self.remove_unused_layers(doc)

        # 2. Processamento de Layers (Mapeamento)
        current_layers = [layer.dxf.name for layer in doc.layers]
        relevant_rules = {k: v for k, v in rules.items() if k in current_layers}

        for layer_origem, rule in relevant_rules.items():
            self.ensure_layer(doc, rule.layer_destino, rule.cor, rule.espessura_linha)
            self.move_entities_to_layer(msp, layer_origem, rule.layer_destino)

        # 3. Forçar propriedades ByLayer em tudo (conforme script original)
        for entity in msp:
            entity.dxf.color = 256
            entity.dxf.linetype = 'BYLAYER'
            entity.dxf.lineweight = -1

        # 4. Aplicação de Logos (Se houver arquivo logos.dxf)
        if logos_doc:
            self.apply_logos(doc, logos_doc)
            # Limpa novamente layers que vieram do logo mas podem não ser usados ou duplicados
            self.remove_unused_layers(doc)

        # 5. Nuvem de Revisão
        if options.manter_nuvem_revisao:
             self.apply_revcloud(msp, options.layer_nuvem_origem)

        # 6. Limpeza Final
        self.remove_unused_layers(doc)
        
        return doc

    # --- Métodos Auxiliares ---

    def ensure_layer(self, doc, name: str, color: int, lineweight: int):
        if name not in doc.layers:
            doc.layers.add(name=name, color=color)
        try:
            layer = doc.layers.get(name)
            layer.dxf.color = color
            layer.dxf.lineweight = lineweight
        except Exception:
            pass

    def move_entities_to_layer(self, msp, old_layer: str, new_layer: str):
        try:
            entities = msp.query(f'*[layer=="{old_layer}"]')
            for entity in entities:
                entity.dxf.layer = new_layer
        except Exception as e:
            logger.error(f"Erro ao mover entidades de {old_layer}: {e}")

    def explode_all_inserts(self, msp):
        """Explode blocos recursivamente"""
        max_passes = 5
        for _ in range(max_passes):
            inserts = msp.query('INSERT')
            if not inserts:
                break
            exploded_count = 0
            for entity in inserts:
                try:
                    entity.explode()
                    exploded_count += 1
                except Exception:
                    pass
            if exploded_count == 0:
                break

    def remove_unused_layers(self, doc):
        """Remove layers não usados, preservando 0 e Defpoints"""
        try:
            used_layers: Set[str] = set()
            for entity in doc.chain_layouts_and_blocks():
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
                    used_layers.add(entity.dxf.layer)
            
            used_layers.add("0")
            used_layers.add("Defpoints")
            
            for layer in list(doc.layers):
                name = layer.dxf.name
                if name not in used_layers:
                    try:
                        doc.layers.remove(name)
                    except Exception:
                        pass
        except Exception:
            pass

    def apply_revcloud(self, msp, source_layer):
        try:
            polylines_to_convert = []
            query_str = f'LWPOLYLINE[layer=="{source_layer}"]'
            for entity in msp.query(query_str):
                if entity.is_closed:
                    polylines_to_convert.append(entity)

            for poly in polylines_to_convert:
                points = list(poly.vertices())
                msp.delete_entity(poly)
                revcloud = ezdxf.revcloud.add_entity(msp, points, segment_length=6.0)
                revcloud.dxf.layer = source_layer
        except Exception as e:
            logger.error(f"Erro ao criar nuvem de revisão: {e}")

    def apply_logos(self, target_doc, source_doc):
        """
        Copia entidades do source_doc (logos.dxf) para o target_doc.
        Baseado na função change_logos do seu script original.
        """
        try:
            msp_target = target_doc.modelspace()
            msp_source = source_doc.modelspace()

            # 1. Deletar imagens existentes no destino (para substituir pelo novo logo)
            for image in msp_target.query("IMAGE"):
                msp_target.delete_entity(image)

            # 2. Copiar Linetypes
            for linetype in source_doc.linetypes:
                if linetype.dxf.name not in target_doc.linetypes:
                    try:
                        # Tenta copiar o padrão do linetype
                        pattern = linetype.dxf.pattern if hasattr(linetype.dxf, 'pattern') else None
                        desc = linetype.dxf.description if hasattr(linetype.dxf, 'description') else ""
                        if pattern:
                            target_doc.linetypes.add(linetype.dxf.name, pattern=pattern, description=desc)
                    except Exception:
                        pass

            # 3. Copiar Text Styles
            for style in source_doc.styles:
                if style.dxf.name not in target_doc.styles:
                    try:
                        font = style.dxf.font if hasattr(style.dxf, "font") else "arial.ttf"
                        target_doc.styles.add(name=style.dxf.name, font=font)
                    except Exception:
                        pass

            # 4. Copiar Entidades do ModelSpace
            # Nota: Copiar entidades complexas entre documentos pode falhar se dependerem de blocos não copiados.
            # Como limpamos o logos.dxf antes (explode), deve ser seguro copiar como primitivas.
            for entity in msp_source:
                try:
                    new_entity = entity.copy()
                    msp_target.add_entity(new_entity)
                except Exception as e:
                    logger.warning(f"Não foi possível copiar entidade {entity.dxftype()} do logo: {e}")

        except Exception as e:
            logger.error(f"Erro crítico ao aplicar logos: {e}")