import ezdxf
import logging
from typing import Dict, Set, Optional, List
import ezdxf.revcloud
from app.services.layer_mapper import LayerRule

logger = logging.getLogger(__name__)

class DXFProcessorService:
    
    def process_dxf(self, doc, rules: Dict[str, LayerRule], options, logos_doc: Optional[ezdxf.document.Drawing] = None):
        msp = doc.modelspace()
        
        print(f"\n--- PROCESSANDO: Versão DXF {doc.dxfversion} ---")

        # 1. EXPLODIR TUDO
        print("DEBUG: Iniciando explosão recursiva...")
        self.explode_drawing(msp)

        # 2. PURGE BLOCKS
        print("DEBUG: Iniciando purge de blocos...")
        self.purge_blocks(doc)

        # 3. LIMPEZA PRELIMINAR
        self.remove_unused_layers(doc)

        # 4. APLICAÇÃO DE REGRAS
        current_layers = [layer.dxf.name for layer in doc.layers]
        relevant_rules = {k: v for k, v in rules.items() if k in current_layers}
        print(f"DEBUG: {len(relevant_rules)} regras de layer aplicáveis.")

        for layer_origem, rule in relevant_rules.items():
            self.ensure_layer_properties(
                doc, 
                rule.layer_destino, 
                rule.cor, 
                rule.espessura_linha, 
                rule.tipo_linha
            )
            self.change_layer_entities(msp, layer_origem, rule.layer_destino)

        # 5. FORÇAR BYLAYER
        print("DEBUG: Forçando ByLayer Global...")
        self.force_all_bylayer(doc)

        # 6. LOGOS
        if logos_doc:
            print("DEBUG: Inserindo Logos...")
            self.apply_logos(doc, logos_doc)

        # 7. LIMPEZA FINAL
        self.remove_unused_layers(doc)

        # 8. NUVEM DE REVISÃO (CORRIGIDO)
        if options.manter_nuvem_revisao:
            layer_alvo = options.layer_nuvem_origem

            if layer_alvo in rules:
                novo_nome = rules[layer_alvo].layer_destino
                print(f"DEBUG: Layer de nuvem '{layer_alvo}' foi movido para '{novo_nome}'. Usando '{novo_nome}' como alvo.")
                layer_alvo = novo_nome

            print(f"DEBUG: Processando nuvens de revisão no layer '{layer_alvo}'...")
            self.apply_revcloud(msp, layer_alvo, arc_radius=6.0)

        print("--- FIM DO PROCESSAMENTO ---\n")
        return doc

    # =========================================================================
    # LÓGICA DE PROPRIEDADES
    # =========================================================================

    def ensure_layer_properties(self, doc, name: str, color: int, lineweight: int, linetype: str):
        if name not in doc.layers:
            try: 
                doc.layers.add(name=name, color=color)
            except: pass

        try:
            layer = doc.layers.get(name)
            layer.dxf.color = color
            layer.dxf.lineweight = lineweight
            
            if linetype and linetype.strip().upper() not in ['NONE', '', 'NAN']:
                if linetype in doc.linetypes:
                    layer.dxf.linetype = linetype
                elif 'Continuous' in doc.linetypes:
                    layer.dxf.linetype = 'Continuous'
        except Exception as e:
            print(f"ERRO layer {name}: {e}")

    def change_layer_entities(self, msp, old_layer: str, new_layer: str):
        try:
            entities = msp.query(f'*[layer=="{old_layer}"]')
            for entity in entities:
                entity.dxf.layer = new_layer
        except Exception as e:
            logger.error(f"Erro move {old_layer}: {e}")

    def force_all_bylayer(self, doc):
        count = 0
        for entity in doc.chain_layouts_and_blocks():
            if hasattr(entity, 'dxf'):
                self._set_bylayer(entity)
                count += 1
                if entity.dxftype() == 'INSERT':
                    for attrib in entity.attribs: self._set_bylayer(attrib)
                if entity.dxftype() == 'POLYLINE':
                    for vertex in entity.vertices(): self._set_bylayer(vertex)
        print(f"DEBUG: {count} entidades setadas para ByLayer.")

    def _set_bylayer(self, entity):
        try:
            entity.dxf.color = 256
            entity.dxf.lineweight = -1
            entity.dxf.linetype = "BYLAYER"
            entity.dxf.discard('true_color') 
        except: pass

    # =========================================================================
    # LÓGICA DE EXPLOSÃO / PURGE
    # =========================================================================

    def explode_drawing(self, msp):
            iteration = 0
            while iteration < 20:
                inserts = msp.query('INSERT')
                if not inserts: break
                print(f"DEBUG: Explode pass {iteration+1}: {len(inserts)} blocos.")
                exploded_count = 0
                for entity in inserts:
                    try:
                        entity.explode()
                        exploded_count += 1
                    except: pass
                    if entity.is_alive:
                        try: msp.delete_entity(entity)
                        except: pass
                if exploded_count == 0: break
                iteration += 1

    def purge_blocks(self, doc):
        removable = self._get_removable_blocks(doc)
        try: deletion_order = self._get_deletion_order(doc, removable)
        except: deletion_order = sorted(removable, key=len, reverse=True)
        
        count = 0
        for block_name in deletion_order:
            try:
                doc.blocks.delete_block(block_name)
                count += 1
            except: pass
        print(f"DEBUG: {count} blocos purgados.")

    def _get_removable_blocks(self, doc) -> List[str]:
        removable = []
        for block_name in doc.blocks.block_names():
            if block_name.upper().startswith(("*MODEL_SPACE", "*PAPER_SPACE")): continue
            removable.append(block_name)
        return removable

    def _get_deletion_order(self, doc, removable: List[str]) -> List[str]:
        graph = {block: set() for block in removable}
        for block in removable:
            block_def = doc.blocks.get(block)
            for entity in block_def:
                if entity.dxftype() == "INSERT":
                    ref = entity.dxf.name
                    if ref in graph: graph[block].add(ref)
        order = []
        visited = {} 
        def dfs(node):
            if node in visited:
                if visited[node] == 1: raise ValueError("Ciclo")
                return
            visited[node] = 1
            for neighbor in graph[node]: dfs(neighbor)
            visited[node] = 2
            order.append(node)
        for node in graph:
            if node not in visited: dfs(node)
        return list(reversed(order))

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def remove_unused_layers(self, doc):
        try:
            used = set()
            for entity in doc.chain_layouts_and_blocks():
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
                    used.add(entity.dxf.layer)
            used.add("0")
            used.add("Defpoints")
            for layer in list(doc.layers):
                if layer.dxf.name not in used:
                    try: doc.layers.remove(layer.dxf.name)
                    except: pass
        except: pass

    # =========================================================================
    # NUVEM DE REVISÃO (CORRIGIDA - Lógica do seu script)
    # =========================================================================

    def apply_revcloud(self, msp, source_layer, arc_radius=6.0):
        try:
            polylines_vertices = []
            
            # Diagnóstico do Layer
            entities_on_layer = msp.query(f'*[layer=="{source_layer}"]')
            print(f"DEBUG: Total de entidades no layer '{source_layer}': {len(entities_on_layer)}")
            
            for entity in list(msp):
                # Filtra layer (case insensitive)
                if entity.dxf.layer.upper() != source_layer.upper():
                    continue

                # Diagnóstico detalhado de por que foi ignorado
                if entity.dxftype() not in ["LWPOLYLINE", "POLYLINE"]:
                    print(f"DEBUG: Ignorado entidade '{entity.dxftype()}' no layer da nuvem (Esperado: POLYLINE)")
                    continue

                # Verifica se é fechado (Flag ou Geometria)
                is_closed = False
                if entity.is_closed:
                    is_closed = True
                else:
                    # Verifica fechamento visual (Start == End)
                    try:
                        points = list(entity.vertices())
                        if len(points) > 2:
                            # Compara X e Y do primeiro e último ponto (tolerância pequena)
                            start = points[0]
                            end = points[-1]
                            # vertices() retorna (x, y, z, ...), pegamos os 2 primeiros
                            if abs(start[0] - end[0]) < 1e-4 and abs(start[1] - end[1]) < 1e-4:
                                is_closed = True
                                print("DEBUG: Polilinha geometricamente fechada encontrada (Flag is_closed estava False).")
                    except Exception as e:
                        pass
                
                if is_closed:
                    # Coleta vértices
                    try:
                        # Para POLYLINE (legacy) e LWPOLYLINE
                        points = list(entity.vertices())
                        polylines_vertices.append(points)
                        msp.delete_entity(entity)
                    except Exception as e:
                        print(f"ERRO ao ler vértices: {e}")
                else:
                    print(f"DEBUG: Ignorado {entity.dxftype()} aberta (não é um retângulo fechado).")

            # Criação
            created_count = 0
            for points in polylines_vertices:
                try:
                    revcloud = ezdxf.revcloud.add_entity(msp, points, segment_length=arc_radius)
                    revcloud.dxf.layer = source_layer
                    revcloud.dxf.color = 256
                    created_count += 1
                except Exception as e:
                    print(f"ERRO criando RevCloud: {e}")
            
            print(f"DEBUG: {created_count} nuvens de revisão criadas com sucesso.")

        except Exception as e:
            logger.error(f"Erro Crítico em apply_revcloud: {e}")

    # =========================================================================
    # LOGOS
    # =========================================================================

    def apply_logos(self, target_doc, source_doc):
        try:
            msp_t = target_doc.modelspace()
            msp_s = source_doc.modelspace()
            
            print("DEBUG: Preparando Logo...")
            self.explode_drawing(msp_s)
            self.purge_blocks(source_doc)

            for img in msp_t.query("IMAGE"): msp_t.delete_entity(img)

            for lt in source_doc.linetypes:
                if lt.dxf.name not in target_doc.linetypes:
                    try: target_doc.linetypes.add(lt.dxf.name)
                    except: pass
            
            for st in source_doc.styles:
                style_name = st.dxf.name
                if style_name not in target_doc.styles:
                    try: 
                        font = st.dxf.font if hasattr(st.dxf, "font") else "arial.ttf"
                        target_doc.styles.add(name=style_name, font=font)
                    except: pass
            
            print("DEBUG: Copiando entidades do Logo...")
            for e in msp_s:
                try:
                    new_entity = e.copy() 
                    msp_t.add_entity(new_entity)
                except: pass
        except Exception as e:
            logger.error(f"Logo error: {e}")