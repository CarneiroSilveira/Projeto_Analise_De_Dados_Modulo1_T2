# Projeto Avaliativo SCTEC Módulo 1 — Pipeline de Dados Viagens a Serviço (Portal da Transparência)


**Feito Por:** Ian Félix Carneiro Silveira

Pipeline de dados completo, construído em Python e MySQL, para transformar os dados públicos de **Viagens a Serviço** do Portal da Transparência em informações prontas para análise e tomada de decisão. O projeto segue a **Arquitetura Medallion** (Raw → Silver → Gold), passando pela extração automatizada dos dados, tipagem e integridade referencial, até a construção de uma camada analítica com perguntas de negócio respondidas por SQL, tabelas e gráficos.

**Repositório:** [CarneiroSilveira/Projeto_Analise_De_Dados_Modulo1_T2](https://github.com/CarneiroSilveira/Projeto_Analise_De_Dados_Modulo1_T2)

## Objetivo

O objetivo deste projeto é pegar um dado público, bruto e difícil de usar no dia a dia, e transformá-lo em uma base organizada, confiável e pronta para responder perguntas reais de negócio. Ou seja: sair de um arquivo cheio de inconsistências e chegar a gráficos e números que qualquer pessoa consegue olhar e entender.

## Qual problema resolve?

O governo disponibiliza os dados de viagens a serviço para o público, mas em um formato bruto e confuso: números com vírgula no lugar de ponto, datas em texto, informações espalhadas em várias tabelas e cheias de inconsistências. Na prática, isso torna quase impossível confiar nesse dado ou usá-lo para tomar qualquer decisão sem antes organizá-lo.

Este projeto resolve esse problema construindo um pipeline que:

- Baixa os dados direto da fonte oficial, sem precisar baixar nada manualmente;
- Guarda uma cópia fiel do dado original, para que seja sempre possível conferir de onde cada número veio;
- Limpa, corrige e organiza os dados, eliminando erros, duplicidades e inconsistências de formato;
- Transforma tudo isso em respostas prontas para perguntas reais de negócio, com tabelas e gráficos fáceis de entender.

Em resumo: o projeto pega um dado público bruto e difícil de usar, e devolve informação organizada e confiável, pronta para apoiar decisões.

## Tecnologias utilizadas

- **Python** — linguagem principal do pipeline
- **Pandas** — leitura, limpeza e transformação dos dados
- **MySQL** — armazenamento das camadas Raw, Silver e Gold
- **mysql-connector-python** — conexão entre Python e o banco
- **Matplotlib** — geração dos gráficos de análise
- **Jupyter Notebook** — construção da camada Gold e das análises de negócio
- **python-dotenv** — leitura segura das credenciais no `.env`
- **gdown** — download automatizado do arquivo `.zip` direto do Google Drive
- **gc (garbage collector)** — liberação de memória durante a leitura dos CSVs em blocos, mantendo o processo leve mesmo com uma base de dados grande

### Arquitetura do pipeline

```
Google Drive (.zip com 4 CSVs)
        │
        ▼
 extrair.py ──────────► RAW (raw_viagem, raw_pagamento, raw_passagem, raw_trecho)
        │                  todas as colunas VARCHAR, cópia fiel do CSV
        ▼
 transformar.py ──────► SILVER (silver_viagem, silver_pagamento, silver_passagem, silver_trecho)
        │                  tipagem correta, PK, FK, constraints
        ▼
 analise.ipynb ─────────► GOLD (tabelas + views agregadas via JOIN + GROUP BY)
                           7 perguntas de negócio + tabelas + gráficos
```

## Como executar o projeto

1. Clone o repositório:

```bash
git clone https://github.com/CarneiroSilveira/Projeto_Analise_De_Dados_Modulo1_T2.git
```

2. Acesse a pasta do projeto:

```bash
cd Projeto_Analise_De_Dados_Modulo1_T2
```

3. Crie e ative o ambiente virtual (venv).

**Linux/macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (Prompt de Comando)**

```bash
python -m venv venv
venv\Scripts\activate
```

4. Instale as dependências do projeto:

```bash
pip install -r requirements.txt
```

O arquivo `requirements.txt` contém todas as bibliotecas necessárias para a execução do projeto, incluindo o **ipykernel**, utilizado para rodar o notebook dentro do ambiente virtual.

5. Configure as variáveis de ambiente:

- Copie o arquivo `.env.exemple` para `.env`;
- Preencha os dados de conexão do MySQL (host, usuário, senha, nome do banco);
- Preencha o `DRIVE_FILE_ID` com o ID do arquivo `.zip` no Google Drive, em `config.py`.

6. Crie o banco de dados e as tabelas:

Execute o script `criar_banco.sql` no MySQL. Ele cria o banco e as 8 tabelas (4 Raw + 4 Silver), já com chaves primárias, estrangeiras e demais constraints.

7. Execute os scripts na seguinte ordem:

```bash
python src/extrair.py
python src/transformar.py
```

- `1_extrair.py`: baixa o `.zip` do Google Drive (com `gdown`), lê os 4 CSVs em blocos e carrega na camada Raw (processo idempotente, com `TRUNCATE` antes da carga, e resiliente, com `try/except`);
- `2_transformar.py`: copia os dados da Raw para a Silver, convertendo tipos (texto → `DECIMAL` e `DATE`), respeitando a integridade referencial e calculando as colunas `valor_total` e `duracao_dias`.

8. Abra o `notebook/analise.ipynb` no Jupyter ou VS Code, selecione o kernel do ambiente virtual (`venv`) e execute todas as células em ordem. O notebook responde às 7 perguntas de negócio e constrói a camada Gold (tabelas e views).

## Estrutura do projeto

```
.
├── notebook/
│   └── analise.ipynb
├── src/
│   ├── extrair.py
│   ├── transformar.py
│   ├── config.py
│   └── banco.py
├── assets/
├── criar_banco.sql
├── requirements.txt
├── .env.exemple
├── .gitignore
└── README.md
```

## Camada Raw

Cópia fiel dos 4 CSVs originais (`2025_Viagem.csv`, `2025_Pagamento.csv`, `2025_Passagem.csv`, `2025_Trecho.csv`), sem nenhuma transformação. Todas as colunas são `VARCHAR`, sem constraints, preservando inclusive colunas que a Silver não utiliza (como `cpf_viajante` e dados de volta da passagem), para garantir rastreabilidade total.

| Tabela | Conteúdo |
|---|---|
| `raw_viagem` | Dados gerais de cada viagem |
| `raw_pagamento` | Pagamentos realizados por viagem |
| `raw_passagem` | Passagens emitidas por viagem |
| `raw_trecho` | Trechos percorridos em cada viagem |

## Camada Silver

Dados limpos, tipados corretamente (`DECIMAL`, `DATE`, `INT`) e com integridade referencial entre as tabelas via chave estrangeira `id_viagem`.

| Transformação Raw → Silver | Resultado |
|---|---|
| Chaves primárias | `id_viagem` (Viagem) e `id_passagem`, `id_pagamento`, `id_trecho` (`AUTO_INCREMENT`) |
| Chaves estrangeiras | `id_viagem` em `silver_passagem`, `silver_pagamento` e `silver_trecho`, referenciando `silver_viagem` |
| Coluna `valor_total` | Calculada em `silver_viagem` a partir de diárias, passagens, devolução e outros gastos |
| Coluna `duracao_dias` | Calculada em `silver_viagem` a partir das datas de início e fim |
| Tipos de dados | Conversão de `VARCHAR` para `DECIMAL` e `DATE` |
| Valores monetários | Texto com vírgula decimal (`1272,97`) convertido para `DECIMAL(10,2)` |
| Datas | Texto `DD/MM/AAAA` convertido para `DATE` |

### Constraints (2 por tabela, 8 no total)

| Tabela | Constraint 1 | Constraint 2 |
|---|---|---|
| `silver_viagem` | `NOT NULL` em `nome_orgao_superior` | `CHECK` em `valor_diarias >= 0` |
| `silver_pagamento` | `CHECK` em `valor >= 0` | `NOT NULL` em `tipo_pagamento` |
| `silver_passagem` | `CHECK` em `valor_passagem >= 0` | `CHECK` em `taxa_servico >= 0` |
| `silver_trecho` | `CHECK` em `numero_diarias >= 0` | `UNIQUE` em `(id_viagem, sequencia_trecho)` |

## Camada Gold

Construída a partir da Silver, com consultas `JOIN` + `GROUP BY`, agregando por órgão, tipo de pagamento, UF de destino e meio de transporte. Criada tanto como **tabela materializada** quanto como **view**, para permitir tanto consultas rápidas quanto atualização automática quando a Silver mudar.

| Tabela | View |
|---|---|
| `gold_pagamentos` | `view_gold_pagamentos` |
| `gold_trechos` | `view_gold_trechos` |

## Perguntas de negócio respondidas

1. Os 5 órgãos com maior custo total?
2. Os 3 destinos com maior custo médio por viagem?
3. A viagem de maior duração e seu custo total?
4. Qual o tipo de pagamento com maior valor médio?
5. Qual o meio de transporte mais usado nos trechos?
6. Qual UF de destino aparece em mais trechos?
7. Qual órgão pagou mais no total?

Cada pergunta é respondida no notebook `notebook/analise.ipynb` com consulta SQL, tabela de resultado e gráfico correspondente.

## Conclusões e insights

Olhando para os resultados das análises, alguns pontos chamam atenção:

1. **O gasto está concentrado em poucos órgãos.** Um pequeno grupo de órgãos responde pela maior parte do custo total com viagens, o que os torna o primeiro lugar a olhar em qualquer política de redução de gastos;
2. **Nem sempre "caro" significa "frequente".** Os destinos com maior custo médio por viagem costumam ser lugares mais distantes ou com poucas viagens registradas — ou seja, são casos pontuais, não o padrão da maioria das viagens;
3. **Viagem longa não é sinônimo de viagem cara.** A viagem de maior duração não é necessariamente a de maior custo total, o que mostra que o valor gasto depende mais do tipo de despesa do que do tempo fora;
4. **Passagens pesam mais no bolso do que diárias.** Entre os tipos de pagamento, passagens e indenizações têm o maior valor médio, enquanto as diárias, embora mais recorrentes, custam menos por unidade;
5. **O avião ainda domina.** O transporte aéreo é o meio mais usado nos trechos das viagens, com o transporte rodoviário aparecendo mais em deslocamentos curtos;
6. **Brasília concentra os destinos.** A UF de destino mais frequente e o órgão que mais gasta reforçam o papel da capital como polo de deslocamentos institucionais;
7. **O pipeline é consistente.** O órgão apontado como maior gastador na camada Gold é o mesmo identificado diretamente na Silver, o que dá confiança de que os dados não se perderam ou se distorceram ao longo das transformações.

## Melhorias futuras

- Criar um dashboard interativo (por exemplo, no Power BI), para que qualquer pessoa possa explorar os dados sem precisar mexer em código;
- Automatizar a execução do pipeline por completo, com atualização periódica dos dados sem intervenção manual;
- Adicionar verificações automáticas de qualidade dos dados antes de liberar a camada Silver, pegando erros antes que cheguem até a análise;
- Ampliar a camada Gold com novas visões, como evolução do gasto mês a mês ou por viajante;
