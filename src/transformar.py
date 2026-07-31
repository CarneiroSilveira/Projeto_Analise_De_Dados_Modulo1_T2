import sys
import gc
import warnings
from datetime import datetime
from decimal import Decimal, InvalidOperation
import pandas as pd

from src.banco import conectar, executar, inserir_em_lote

warnings.filterwarnings('ignore', message='.*pandas only supports SQLAlchemy.*')


def texto_para_decimal(valor):
    """
    Converte valores numéricos em formato de texto (com vírgula ou ponto) 
    para o tipo Decimal, retornando None se o valor for inválido ou nulo.
    """
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if texto == "" or texto.upper() in ("NAN", "NA", "NULL"):
        return None
    try:
        texto = texto.replace(".", "").replace(",", ".")
        return Decimal(texto)
    except (InvalidOperation, ValueError):
        return None


def texto_para_data(valor):
    """
    Transforma uma string de data (ignorando a parte da hora) 
    em um objeto datetime.date. Retorna None para formatos inválidos.
    """
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip().split(" ")[0]
    if texto == "" or texto.upper() in ("NAN", "NA", "NULL"):
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def texto_ou_none(valor):
    """
    Remove espaços em branco de uma string. Se o texto for vazio ou 
    indicar valor nulo (ex: 'NaN'), retorna None.
    """
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if texto == "" or texto.upper() in ("NAN", "NA", "NULL"):
        return None
    return texto


def texto_para_int(valor):
    """
    Converte um valor recebido para número inteiro. 
    Lida primeiro com possíveis decimais retornando apenas a parte inteira.
    """
    texto = texto_ou_none(valor)
    if texto is None:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError:
        return None


def ler_tabela_raw_em_lotes(conexao_leitura, nome_tabela: str, tamanho_lote: int = 50000):
    """
    Lê os dados do banco de dados em lotes (chunks) para otimizar 
    o uso de memória durante o processamento de tabelas muito grandes.
    """
    return pd.read_sql(f"SELECT * FROM {nome_tabela}", conexao_leitura, chunksize=tamanho_lote)


def transformar_viagem(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Mapeia e limpa a tabela de viagens. Aplica conversões de tipos, 
    calcula os valores totais e a duração de cada viagem em dias, 
    removendo registros inválidos ou duplicados.
    """
    df = pd.DataFrame()
    df["id_viagem"] = df_raw["identificador_do_processo_de_viagem"].map(texto_ou_none)
    df["num_proposta"] = df_raw["numero_da_proposta"].map(texto_ou_none)
    df["situacao"] = df_raw["situacao"].map(texto_ou_none)
    df["viagem_urgente"] = df_raw["viagem_urgente"].map(texto_ou_none)
    df["cod_orgao_superior"] = df_raw["codigo_do_orgao_superior"].map(texto_ou_none)
    df["nome_orgao_superior"] = df_raw["nome_do_orgao_superior"].map(texto_ou_none)
    df["nome_viajante"] = df_raw["nome_viajante"].map(texto_ou_none)
    df["cargo"] = df_raw["cargo"].map(texto_ou_none)
    df["data_inicio"] = df_raw["periodo_data_de_inicio"].map(texto_para_data)
    df["data_fim"] = df_raw["periodo_data_de_fim"].map(texto_para_data)
    df["destinos"] = df_raw["destinos"].map(texto_ou_none)
    df["motivo"] = df_raw["motivo"].map(texto_ou_none)
    df["valor_diarias"] = df_raw["valor_diarias"].map(texto_para_decimal)
    df["valor_passagens"] = df_raw["valor_passagens"].map(texto_para_decimal)
    df["valor_devolucao"] = df_raw["valor_devolucao"].map(texto_para_decimal)
    df["valor_outros_gastos"] = df_raw["valor_outros_gastos"].map(texto_para_decimal)

    def soma_valores(linha):
        """Função auxiliar para somar todos os custos válidos da viagem."""
        partes = [linha["valor_diarias"], linha["valor_passagens"],
                  linha["valor_devolucao"], linha["valor_outros_gastos"]]
        return sum((p for p in partes if p is not None), Decimal("0.00"))

    df["valor_total"] = df.apply(soma_valores, axis=1)

    def calcula_duracao(linha):
        """Função auxiliar para calcular a quantidade de dias da viagem."""
        if pd.notna(linha["data_inicio"]) and pd.notna(linha["data_fim"]):
            return (linha["data_fim"] - linha["data_inicio"]).days + 1
        return None

    df["duracao_dias"] = df.apply(calcula_duracao, axis=1)
    
    df = df.dropna(subset=["id_viagem", "nome_orgao_superior"])
    df = df[(df["valor_diarias"].isna()) | (df["valor_diarias"] >= 0)]
    df = df.dropna(subset=["data_inicio", "data_fim"])
    df = df[df["data_fim"] >= df["data_inicio"]]
    df = df.drop_duplicates(subset=["id_viagem"])
    
    return df


def transformar_pagamento(df_raw: pd.DataFrame, ids_validos: set) -> pd.DataFrame:
    """
    Transforma a tabela de pagamentos, convertendo valores numéricos e 
    mantendo apenas registros associados a viagens previamente validadas.
    """
    df = pd.DataFrame()
    df["id_viagem"] = df_raw["identificador_do_processo_de_viagem"].map(texto_ou_none)
    df["num_proposta"] = df_raw["numero_da_proposta"].map(texto_ou_none)
    df["nome_orgao_pagador"] = df_raw["nome_do_orgao_pagador"].map(texto_ou_none)
    df["nome_ug_pagadora"] = df_raw["nome_da_unidade_gestora_pagadora"].map(texto_ou_none)
    df["tipo_pagamento"] = df_raw["tipo_de_pagamento"].map(texto_ou_none)
    df["valor"] = df_raw["valor"].map(texto_para_decimal)

    df = df.dropna(subset=["id_viagem", "tipo_pagamento"])
    df = df[df["id_viagem"].isin(ids_validos)]
    df = df[(df["valor"].isna()) | (df["valor"] >= 0)]
    
    return df


def transformar_passagem(df_raw: pd.DataFrame, ids_validos: set) -> pd.DataFrame:
    """
    Transforma a tabela de passagens, formatando datas e valores financeiros. 
    Filtra os dados para garantir que pertencem a viagens válidas.
    """
    df = pd.DataFrame()
    df["id_viagem"] = df_raw["identificador_do_processo_de_viagem"].map(texto_ou_none)
    df["meio_transporte"] = df_raw["meio_de_transporte"].map(texto_ou_none)
    df["pais_origem_ida"] = df_raw["pais_origem_ida"].map(texto_ou_none)
    df["uf_origem_ida"] = df_raw["uf_origem_ida"].map(texto_ou_none)
    df["cidade_origem_ida"] = df_raw["cidade_origem_ida"].map(texto_ou_none)
    df["pais_destino_ida"] = df_raw["pais_destino_ida"].map(texto_ou_none)
    df["uf_destino_ida"] = df_raw["uf_destino_ida"].map(texto_ou_none)
    df["cidade_destino_ida"] = df_raw["cidade_destino_ida"].map(texto_ou_none)
    df["valor_passagem"] = df_raw["valor_da_passagem"].map(texto_para_decimal)
    df["taxa_servico"] = df_raw["taxa_de_servico"].map(texto_para_decimal)
    df["data_emissao"] = df_raw["data_da_emissao_compra"].map(texto_para_data)

    df = df.dropna(subset=["id_viagem"])
    df = df[df["id_viagem"].isin(ids_validos)]
    df = df[(df["valor_passagem"].isna()) | (df["valor_passagem"] >= 0)]
    df = df[(df["taxa_servico"].isna()) | (df["taxa_servico"] >= 0)]
    
    return df


def transformar_trecho(df_raw: pd.DataFrame, ids_validos: set) -> pd.DataFrame:
    """
    Transforma a tabela de trechos. Valida tipos de origem/destino e datas, 
    mantém trechos atrelados a viagens válidas e remove sequências duplicadas.
    """
    df = pd.DataFrame()
    df["id_viagem"] = df_raw["identificador_do_processo_de_viagem"].map(texto_ou_none)
    df["sequencia_trecho"] = df_raw["sequencia_trecho"].map(texto_para_int)
    df["origem_data"] = df_raw["origem_data"].map(texto_para_data)
    df["origem_uf"] = df_raw["origem_uf"].map(texto_ou_none)
    df["origem_cidade"] = df_raw["origem_cidade"].map(texto_ou_none)
    df["destino_data"] = df_raw["destino_data"].map(texto_para_data)
    df["destino_uf"] = df_raw["destino_uf"].map(texto_ou_none)
    df["destino_cidade"] = df_raw["destino_cidade"].map(texto_ou_none)
    df["meio_transporte"] = df_raw["meio_de_transporte"].map(texto_ou_none)
    df["numero_diarias"] = df_raw["numero_diarias"].map(texto_para_decimal)

    df = df.dropna(subset=["id_viagem"])
    df = df[df["id_viagem"].isin(ids_validos)]
    df = df[(df["numero_diarias"].isna()) | (df["numero_diarias"] >= 0)]
    df = df.drop_duplicates(subset=["id_viagem", "sequencia_trecho"])
    
    return df


def carregar_dataframe(conexao_escrita, df: pd.DataFrame, tabela: str, colunas: list) -> int:
    """
    Insere os registros transformados na respectiva tabela do banco de dados 
    utilizando a estratégia de inserção em lotes (batch insert).
    Retorna o número total de linhas inseridas.
    """
    if df.empty:
        return 0
    colunas_sql = ", ".join(f"`{c}`" for c in colunas)
    placeholders = ", ".join(["%s"] * len(colunas))
    sql_insert = f"INSERT INTO {tabela} ({colunas_sql}) VALUES ({placeholders})"

    linhas = [
        tuple(None if v is None or pd.isna(v) else v for v in linha)
        for linha in df[colunas].itertuples(index=False, name=None)
    ]
    
    tamanho_lote = 5000
    for i in range(0, len(linhas), tamanho_lote):
        lote = linhas[i : i + tamanho_lote]
        inserir_em_lote(conexao_escrita, sql_insert, lote)
        
    return len(linhas)


def main():
    """
    Função principal que orquestra todo o processo de ETL (Extração, Transformação e Carga).
    Inicia as conexões, limpa as tabelas destino (Silver) e executa a transformação em blocos 
    tabela por tabela, garantindo a integridade dos dados através dos ids_validos.
    """
    print("== Fase 2: Transformação Raw -> Silver ==\n")

    conexao_leitura = None
    conexao_escrita = None

    try:
        conexao_leitura = conectar()
        conexao_escrita = conectar()
    except Exception as erro:
        print(f"[ERRO] Conexão com o banco falhou: {erro}")
        sys.exit(1)

    try:
        executar(conexao_escrita, "SET FOREIGN_KEY_CHECKS = 0;")
        for tabela in ("silver_trecho", "silver_passagem", "silver_pagamento", "silver_viagem"):
            executar(conexao_escrita, f"TRUNCATE TABLE {tabela};")
        executar(conexao_escrita, "SET FOREIGN_KEY_CHECKS = 1;")
        print("[OK] Tabelas Silver limpas.\n")

        ids_validos = set()

        print("-> Transformando silver_viagem...")
        colunas_viagem = [
            "id_viagem", "num_proposta", "situacao", "viagem_urgente",
            "cod_orgao_superior", "nome_orgao_superior", "nome_viajante", "cargo",
            "data_inicio", "data_fim", "destinos", "motivo", "valor_diarias",
            "valor_passagens", "valor_devolucao", "valor_outros_gastos",
            "valor_total", "duracao_dias",
        ]
        total_viagem = 0
        for bloco in ler_tabela_raw_em_lotes(conexao_leitura, "raw_viagem"):
            df_viagem = transformar_viagem(bloco)
            ids_validos.update(df_viagem["id_viagem"])
            total_viagem += carregar_dataframe(conexao_escrita, df_viagem, "silver_viagem", colunas_viagem)
            del bloco, df_viagem
            gc.collect()
            
        print(f"[OK] {total_viagem} linhas carregadas em silver_viagem.\n")

        print("-> Transformando silver_pagamento...")
        colunas_pagamento = [
            "id_viagem", "num_proposta", "nome_orgao_pagador",
            "nome_ug_pagadora", "tipo_pagamento", "valor",
        ]
        total_pag = 0
        for bloco in ler_tabela_raw_em_lotes(conexao_leitura, "raw_pagamento"):
            df_pagamento = transformar_pagamento(bloco, ids_validos)
            total_pag += carregar_dataframe(conexao_escrita, df_pagamento, "silver_pagamento", colunas_pagamento)
            del bloco, df_pagamento
            gc.collect()
            
        print(f"[OK] {total_pag} linhas carregadas em silver_pagamento.\n")

        print("-> Transformando silver_passagem...")
        colunas_passagem = [
            "id_viagem", "meio_transporte", "pais_origem_ida", "uf_origem_ida",
            "cidade_origem_ida", "pais_destino_ida", "uf_destino_ida",
            "cidade_destino_ida", "valor_passagem", "taxa_servico", "data_emissao",
        ]
        total_pass = 0
        for bloco in ler_tabela_raw_em_lotes(conexao_leitura, "raw_passagem"):
            df_passagem = transformar_passagem(bloco, ids_validos)
            total_pass += carregar_dataframe(conexao_escrita, df_passagem, "silver_passagem", colunas_passagem)
            del bloco, df_passagem
            gc.collect()
            
        print(f"[OK] {total_pass} linhas carregadas em silver_passagem.\n")

        print("-> Transformando silver_trecho...")
        colunas_trecho = [
            "id_viagem", "sequencia_trecho", "origem_data", "origem_uf",
            "origem_cidade", "destino_data", "destino_uf", "destino_cidade",
            "meio_transporte", "numero_diarias",
        ]
        total_trecho = 0
        for bloco in ler_tabela_raw_em_lotes(conexao_leitura, "raw_trecho"):
            df_trecho = transformar_trecho(bloco, ids_validos)
            total_trecho += carregar_dataframe(conexao_escrita, df_trecho, "silver_trecho", colunas_trecho)
            del bloco, df_trecho
            gc.collect()
            
        print(f"[OK] {total_trecho} linhas carregadas em silver_trecho.\n")

    except Exception as erro:
        print(f"[ERRO] Falha durante a transformação: {erro}")
        sys.exit(1)
    finally:
        if conexao_leitura:
            conexao_leitura.close()
        if conexao_escrita:
            conexao_escrita.close()
        print("[OK] Conexões encerradas.")

    print("\n== Fase 2 concluída ==")


if __name__ == "__main__":
    main()