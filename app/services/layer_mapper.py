import pandas as pd
from io import BytesIO
from typing import Dict
from dataclasses import dataclass

@dataclass
class LayerRule:
    """Objeto simples para armazenar a regra de cada layer"""
    layer_origem: str
    layer_destino: str
    cor: int
    tipo_linha: str
    espessura_linha: int

class LayerMapperService:
    # Suas colunas exatas
    REQUIRED_COLUMNS = [
        "currentLayer", 
        "newLayer", 
        "colorID", 
        "lineType", 
        "lineweight"
    ]

    def parse_excel_rules(self, file_content: bytes) -> Dict[str, LayerRule]:
        try:
            # Lê tanto .xlsx quanto .csv dependendo do arquivo enviado, mas vamos focar no pandas lendo bytes
            # Se for CSV, o pandas detecta ou usamos read_csv. Assumindo Excel (.xlsx) por padrão da especificação.
            df = pd.read_excel(BytesIO(file_content))
            
            # Validação básica de colunas
            missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                # Fallback: Tenta ler como CSV se falhar como Excel ou se colunas não baterem?
                # Por enquanto, vamos assumir que o erro é real.
                raise ValueError(f"Colunas faltando no Excel: {', '.join(missing)}")

            # Limpeza igual ao seu script dxfapi.py
            # Remove linhas onde currentLayer é vazio
            df = df.dropna(subset=["currentLayer"])
            
            # Preenchimento de vazios (Logica trazida do seu dxfapi.py)
            df["newLayer"] = df["newLayer"].fillna("fallback").astype(str)
            df["colorID"] = pd.to_numeric(df["colorID"], errors='coerce').fillna(256).astype(int)
            df["lineweight"] = pd.to_numeric(df["lineweight"], errors='coerce').fillna(0.0)
            df["lineType"] = df["lineType"].fillna("continuous").astype(str)
            df["currentLayer"] = df["currentLayer"].astype(str).str.strip()

            rules_map: Dict[str, LayerRule] = {}
            
            for _, row in df.iterrows():
                # Conversão de espessura: 
                # Se Excel tem 0.2 (mm), DXF precisa de 20 (centésimos). 
                # Seu script usava * 10, mas o padrão é * 100. Vou usar * 100 para garantir espessura visível.
                weight_int = int(row['lineweight'] * 100) 
                
                rule = LayerRule(
                    layer_origem=row['currentLayer'],
                    layer_destino=row['newLayer'],
                    cor=row['colorID'],
                    tipo_linha=row['lineType'],
                    espessura_linha=weight_int
                )
                rules_map[row['currentLayer']] = rule

            return rules_map

        except Exception as e:
            raise ValueError(f"Erro ao processar planilha de layers: {str(e)}")