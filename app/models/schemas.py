# app/models/schemas.py
from enum import Enum
from pydantic import BaseModel, Field

class OutputMode(str, Enum):
    MULTIPLOS_ARQUIVOS = "MULTIPLOS_ARQUIVOS"
    ARQUIVO_UNICO = "ARQUIVO_UNICO"

class OutputFormat(str, Enum):
    DXF = "DXF"
    PDF = "PDF"

class ProcessingOptions(BaseModel):
    modo_saida: OutputMode = Field(..., description="Define se gera múltiplos arquivos ou um consolidado")
    formato_saida: OutputFormat = Field(..., description="Formato final do arquivo")
    
    # Configurações de Nuvem de Revisão
    manter_nuvem_revisao: bool = Field(False, description="Se true, converte polylines do layer indicado em nuvens")
    layer_nuvem_origem: str = Field("LAYER099", description="Nome do layer que contém o retângulo da nuvem")
    
    # Configurações de Hachura
    manter_hachuras: bool = Field(False, description="Se true, preserva hachuras")
    layer_hachura_origem: str = Field("LAYER100", description="Nome do layer que contém a hachura (se aplicável)")