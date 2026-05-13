# Bot BCP - Circulares

Monitora diariamente a pagina de circulares do Banco Central del Paraguay:

https://www.bcp.gov.py/web/institucional/circulares

O bot salva HTML bruto, texto limpo, snapshot JSON, relatorio HTML e PDF em:

```text
%USERPROFILE%\Bot BCP
```

O snapshot captura todos os itens de circular presentes no HTML carregado pelo site.
O historico mantem somente as 10 execucoes mais recentes, apagando automaticamente as mais antigas.

## Instalar

```powershell
cd "C:\Projetos Cassuli\Bot BCP"
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Ou, em um PC novo, rode:

```text
instalar_bot_bcp.bat
```

Esse instalador confere o Python, instala as dependencias, baixa o Chromium do Playwright e cria a tarefa diaria das 10h.

## Rodar manualmente

```powershell
python .\extrair_html_bcp.py
```

O navegador visivel e o padrao, porque o site pode pedir verificacao do Cloudflare. Se quiser forcar explicitamente:

```powershell
python .\extrair_html_bcp.py --headed
```

O bot usa um perfil persistente em `%USERPROFILE%\Bot BCP\browser_profile` para reaproveitar a validacao nas proximas execucoes.
O agendamento usa `pythonw.exe` quando disponivel, entao nao abre janela de terminal. O arquivo `executar_bot_bcp.bat` tambem tenta usar `pythonw.exe` e inicia minimizado.

Para iniciar o navegador visivel, mas minimizado:

```powershell
python .\extrair_html_bcp.py --minimized
```

Modo invisivel existe, mas pode ser bloqueado pelo site:

```powershell
python .\extrair_html_bcp.py --headless
```

## Testar com HTML local

```powershell
python .\extrair_html_bcp.py --source-html "CAMINHO_DO_HTML" --base-dir ".\teste_saida" --no-open --no-pdf
```

## Agendar para 10h

```powershell
powershell -ExecutionPolicy Bypass -File .\agendar_bot_bcp.ps1
```

A tarefa usa o modo interativo do usuario atual para permitir que o relatorio seja aberto no navegador.

## Levar Para Outro PC

Compacte a pasta `Bot BCP` e copie para o outro computador. No primeiro uso, execute:

```text
instalar_bot_bcp.bat
```

Depois disso, use `executar_bot_bcp.bat` para rodar manualmente. A pasta de saida sera criada automaticamente em `%USERPROFILE%\Bot BCP`.

## Testar Mudanca

Depois que o bot ja tiver salvo pelo menos um HTML real, rode:

```text
testar_mudanca_bcp.bat
```

Ele cria uma base separada em `%USERPROFILE%\Bot BCP Teste\run_DATA_HORA`, injeta uma circular fake no topo do ultimo HTML salvo e abre um relatorio mostrando a nova circular detectada.
