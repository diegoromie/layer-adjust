import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Generator
from fastapi import UploadFile

class FileManager:
    def __init__(self, base_temp_dir: str = "temp_processing"):
        self.base_temp_dir = base_temp_dir
        os.makedirs(self.base_temp_dir, exist_ok=True)

    def save_upload_file(self, upload_file: UploadFile, dest_folder: Path) -> Path:
        """Salva um arquivo de upload no disco"""
        dest_path = dest_folder / upload_file.filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return dest_path

    def extract_zip(self, zip_path: Path, extract_to: Path) -> List[Path]:
        """Extrai ZIP e retorna lista de caminhos dos arquivos DXF extraídos"""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        
        # Retorna apenas arquivos .dxf (ignorando pastas ou arquivos ocultos/lixo)
        dxf_files = []
        for root, _, files in os.walk(extract_to):
            for file in files:
                if file.lower().endswith(".dxf"):
                    dxf_files.append(Path(root) / file)
        return dxf_files

    def create_zip(self, folder_path: Path, output_filename: str) -> Path:
        """Compacta uma pasta inteira em um arquivo ZIP"""
        zip_path = folder_path.parent / output_filename
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = Path(root) / file
                    # Salva no ZIP com caminho relativo (sem pastas absolutas do servidor)
                    arcname = file_path.relative_to(folder_path)
                    zipf.write(file_path, arcname)
        return zip_path

    def clean_up(self, folder_path: Path):
        """Remove diretório temporário"""
        shutil.rmtree(folder_path, ignore_errors=True)