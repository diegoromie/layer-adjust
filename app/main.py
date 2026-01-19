from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router

# Metadados da API
app = FastAPI(
    title="Processador de Layers DXF",
    description="API Backend rodando na Oracle Cloud via Cloudflare Tunnel.",
    version="1.0.0",
    # Estas configurações ajudam o Swagger a funcionar corretamente atrás do túnel HTTPS
    root_path="",
    docs_url="/docs",
    redoc_url="/redoc"
)

# --- Configuração de CORS ---
# O frontend (Lovable) fará requisições para layeradj.vizeng.shop.
# O navegador precisa saber que isso é permitido.
origins = [
    "*",  # Permite qualquer origem (Ideal para dev/Lovable).
    # "https://seu-projeto-lovable.lovable.app", # Em produção, use a URL exata do Lovable
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclui as rotas
app.include_router(api_router, prefix="/api")

# Health Check
@app.get("/")
def read_root():
    return {
        "status": "online", 
        "server": "Oracle Cloud", 
        "port": 8013,
        "message": "Backend DXF operando corretamente"
    }

# Bloco de execução
if __name__ == "__main__":
    import uvicorn
    # Rodando na porta 8013 conforme solicitado
    # forwarded_allow_ips='*' é importante para o Cloudflare Tunnel passar os IPs reais
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8013, 
        reload=True,
        proxy_headers=True, 
        forwarded_allow_ips='*' 
    )