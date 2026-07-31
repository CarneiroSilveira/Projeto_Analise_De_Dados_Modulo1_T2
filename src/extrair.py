import sys
import zipfile
import traceback
import mysql.connector
from pathlib import Path
import gdown
import pandas as pd

from src.config import (
    ARQUIVOS,
    CSV_ENCODING,
    CSV_SEPARADOR,
    DRIVE_FILE_ID,
    PASTA_DADOS,
    TAMANHO_BLOCO,
)
from src.banco import conectar, executar, inserir_em_lote


def baixar_zip_do_drive(file_id: str, destino: Path) -> Path:
    """
    Faz o download de um arquivo do Google Drive a partir do seu ID e o salva
    no caminho de destino especificado. Cria as pastas necessárias caso não existam.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        resultado = gdown.download(id=file_id, output=str(destino), quiet=False)
        if resultado is None:
            raise RuntimeError("Falha ao baixar o arquivo: o download não pôde ser concluído.")
        print(f"[OK] Download concluído: {destino}")
        return destino
    except Exception as erro:
        raise RuntimeError(f"Falha ao baixar o arquivo do Google Drive: {erro}")


def extrair_zip(caminho_zip: Path, pasta_destino: Path) -> None:
    """
    Abre o arquivo .zip baixado e descompacta todo o seu conteúdo
    dentro da pasta de destino indicada.
    """
    try:
        with zipfile.ZipFile(caminho_zip, "r") as zip_ref:
            zip_ref.extractall(pasta_destino)
        print(f"[OK] Arquivos extraídos em: {pasta_destino}")
    except zipfile.BadZipFile as erro:
        raise RuntimeError(f"O arquivo baixado não é um .zip válido: {erro}")


def colunas_da_tabela(conexao, tabela: str) -> list:
    """
    Consulta o esquema do banco de dados (information_schema) para descobrir e 
    retornar o nome de todas as colunas de uma tabela específica, na ordem correta.
    """
    cur = conexao.cursor()
    cur.execute("""
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """, (tabela,))
    cols = [r[0] for r in cur.fetchall()]
    cur.close()
    return cols


def carregar_csv_na_raw(conexao, caminho_csv: Path, tabela_raw: str) -> int:
    """
    Limpa a tabela raw de destino e carrega os dados do arquivo CSV para o banco 
    de dados. A leitura e inserção são feitas em lotes (chunks) para economizar 
    memória e garantir a correspondência correta entre as colunas do CSV e da tabela.
    """
    if not caminho_csv.exists():
        raise FileNotFoundError(f"CSV não encontrado: {caminho_csv}")

    executar(conexao, f"TRUNCATE TABLE {tabela_raw};")

    cols_tabela = colunas_da_tabela(conexao, tabela_raw)

    total_linhas = 0
    leitor = pd.read_csv(
        caminho_csv,
        sep=CSV_SEPARADOR,
        encoding=CSV_ENCODING,
        dtype=str,
        keep_default_na=False,
        chunksize=TAMANHO_BLOCO, 
    )

    for bloco in leitor:
        if len(bloco.columns) > len(cols_tabela):
            bloco = bloco.iloc[:, :len(cols_tabela)]
            
        if len(bloco.columns) != len(cols_tabela):
            raise RuntimeError(
                f"{tabela_raw}: CSV tem {len(bloco.columns)} colunas "
                f"mas a tabela exige {len(cols_tabela)} {cols_tabela}"
            )
        bloco.columns = cols_tabela
        
        colunas = list(bloco.columns)
        placeholders = ", ".join(["%s"] * len(colunas))
        colunas_sql = ", ".join(f"`{c}`" for c in colunas)
        sql_insert = f"INSERT INTO {tabela_raw} ({colunas_sql}) VALUES ({placeholders})"

        linhas = [tuple(linha) for tabular in [bloco.itertuples(index=False, name=None)] for linha in tabular]
        
        tamanho_sub_lote = 500
        for i in range(0, len(linhas), tamanho_sub_lote):
            sub_lote = linhas[i:i + tamanho_sub_lote]
            inserir_em_lote(conexao, sql_insert, sub_lote)
            
        total_linhas += len(linhas)
        print(f"    ... {total_linhas} linhas processadas e enviadas para {tabela_raw}")

    return total_linhas


def main():
    """
    Função principal que gerencia o fluxo geral: baixa o arquivo de dados do Drive, 
    descompacta o arquivo zip e itera sobre as configurações para carregar cada 
    arquivo CSV resultante na sua respectiva tabela no banco de dados.
    """
    caminho_zip = PASTA_DADOS / "viagens_2025.zip"

    try:
        if not caminho_zip.exists():
            if DRIVE_FILE_ID == "COLE_AQUI_O_ID_DO_ARQUIVO_NO_DRIVE":
                raise RuntimeError("Configure DRIVE_FILE_ID em config.py")
            baixar_zip_do_drive(DRIVE_FILE_ID, caminho_zip)
        else:
            print(f"[OK] Arquivo zip já existe em: {caminho_zip}. Pulando download.")
    except Exception as erro:
        print(f"[ERRO] Download falhou: {erro}")
        sys.exit(1)

    try:
        csvs_pendentes = [info["csv"] for _, info in ARQUIVOS.items() if not (PASTA_DADOS / info["csv"]).exists()]
        
        if csvs_pendentes:
            extrair_zip(caminho_zip, PASTA_DADOS)
        else:
            print("[OK] Arquivos CSV já extraídos. Pulando extração.")
    except Exception as erro:
        print(f"[ERRO] Extração falhou: {erro}")
        sys.exit(1)

    for chave, info in ARQUIVOS.items():
        caminho_csv = PASTA_DADOS / info["csv"]
        tabela_raw = info["tabela_raw"]
        print(f"\n-> Carregando '{info['csv']}' em '{tabela_raw}'...")
        
        conexao = None
        try:
            conexao = conectar()
            total = carregar_csv_na_raw(conexao, caminho_csv, tabela_raw)
            print(f"[OK] {total} linhas carregadas com sucesso em {tabela_raw}.")
        except mysql.connector.Error as erro:
            print(f"[ERRO] MySQL {erro.errno} ({erro.sqlstate}): {erro.msg}")
            traceback.print_exc()
        except Exception as erro:
            print(f"[ERRO] Falha ao carregar {info['csv']}: {erro!r}")
            traceback.print_exc()
        finally:
            if conexao:
                try:
                    conexao.close()
                except Exception:
                    pass

    print("\n[OK] Processo de carga finalizado.")


if __name__ == "__main__":
    main()