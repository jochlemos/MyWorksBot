# Mywork Ponto Bot

Aplicativo desktop para Windows que automatiza o registro de ponto no **Mywork** (entrada, pausa, retorno, saída) via navegador controlado pelo **Playwright**, com agendamento por perfil, execução em segundo plano e credenciais protegidas localmente.

**Documentação detalhada (cada tela, campo e função):** [docs/GUIA_DO_SISTEMA.md](docs/GUIA_DO_SISTEMA.md)

---

## Sumário

- [Guia do sistema (telas e campos)](docs/GUIA_DO_SISTEMA.md)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Executar](#executar)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Uso da interface](#uso-da-interface)
- [Configuração](#configuração)
- [Agendamentos](#agendamentos)
- [Robô (Playwright)](#robô-playwright)
- [Dados e arquivos locais](#dados-e-arquivos-locais)
- [Build do executável](#build-do-executável)
- [Observações legais e de uso](#observações-legais-e-de-uso)

---

## Requisitos

- **Windows** 10 ou 11
- **Python 3.11+** (desenvolvimento e build)
- Conta e acesso ao site Mywork conforme política da sua organização

---

## Instalação

```powershell
cd caminho\para\mywork-ponto-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Executar

```powershell
python main.py
```

Iniciar minimizado (útil com “Iniciar com Windows”):

```powershell
python main.py --minimized
```

---

## Estrutura do projeto

| Caminho | Função |
|--------|--------|
| `main.py` | Ponto de entrada Qt, `AppController`, ciclo de vida do app |
| `src/ui_main.py` | Janela principal, abas, relógio, agendamentos na UI |
| `src/api_client.py` | Automação: login, navegação até ponto, batida, etapas logáveis |
| `src/scheduler_service.py` | Thread do agendador, disparo automático nos horários |
| `src/storage.py` | Leitura/gravação de `config.json`, logs, histórico, estado em runtime |
| `src/security.py` | Credenciais com DPAPI (Windows) |
| `src/models.py` | `AppConfig`, `ScheduleProfile`, `ScheduleEvent`, etc. |
| `src/startup.py` | Registro em “Iniciar com Windows” (HKCU Run) |

---

## Uso da interface

### Tela inicial

- **Próximos agendamentos:** até 3 próximos eventos do(s) perfil(is) ativo(s).
- **Relógio:** hora atual (atualização por segundo).
- **Status:** mensagens resumidas (ex.: agendador ativo, notificações de batida).

### Abas

1. **Configuração** — URLs, seletores, tolerância, opções de navegador e início com Windows; botões **Salvar configuração** e **Testar login robô**.
2. **Agendamentos** — Nome do perfil, dias da semana, lista de eventos (`HH:MM` + tipo + descrição opcional), salvar perfil.
3. **Histórico** — Registros de batidas (sucesso/falha, origem manual/auto).
4. **Logs** — Log textual da aplicação e **etapas do robô** durante testes e batidas manuais iniciadas pela UI.

Ao iniciar uma operação longa do robô (teste de login, bater ponto manual, teste de registro), o app **muda para a aba Logs** e registra cada etapa. Há um **tempo limite de 300 segundos (5 min)** na UI: se ultrapassar, é exibido aviso e o resultado final dessa operação não dispara o diálogo de conclusão (a tarefa pode ainda terminar em segundo plano).

### Bandeja do sistema

Fechar a janela envia o app para a bandeja; use o menu do ícone para abrir ou sair.

---

## Configuração

1. Preencha **e-mail** e **senha** (a senha é guardada com **DPAPI** no perfil do Windows).
2. **URL de login** e **URL da página de ponto** devem apontar para o ambiente correto do Mywork.
3. **Seletores CSS** precisam bater com o HTML atual do site. Se o layout mudar, atualize:
   - campo e-mail, senha, botão de login, botão/ação de bater ponto.
4. **Bloquear descrição repetida no site** evita enviar a mesma descrição da última linha do histórico visível (comportamento do robô).
5. **Tolerância (minutos)** define a janela em torno do horário agendado em que o agendador tenta registrar o ponto automaticamente.
6. **Headless** executa o Chromium sem janela visível (quando aplicável ao fluxo).

Descrições padrão por tipo de batida continuam existindo internamente no `config.json` para fallback quando um evento **não** tem descrição própria; a interface de configuração não expõe mais esses quatro campos — a descrição principal é configurada **por evento** na aba Agendamentos.

---

## Agendamentos

- Um **perfil** tem: nome, ativo/inativo, dias da semana (0 = segunda … 6 = domingo) e uma lista de **eventos**.
- Cada evento: **`HH:MM`**, **tipo** (`entrada`, `pausa`, `retorno`, `saida`) e **descrição opcional** (texto enviado ao site como motivo).
- Formato no editor de texto (uma linha por evento):

  `HH:MM tipo` ou `HH:MM tipo texto da descrição`

- **Não é permitido** dois eventos no **mesmo horário** (mesmo minuto do dia) no mesmo perfil — validação ao adicionar linha e ao salvar.
- Botões **Remover último** e **Remover linha atual** ajudam a editar a lista.

O agendador roda em **thread separada** e, nos horários configurados, chama o mesmo fluxo de registro do robô.

---

## Robô (Playwright)

- Após preencher e enviar o login, o cliente **espera sinais de sucesso** (URL, elementos da área logada ou da página de ponto) antes de seguir; em caso de erro visível na tela de login, a operação falha com mensagem clara.
- Operações pesadas disparadas pela UI rodam em **thread em segundo plano** para não travar a janela; atualizações de log e notificações são encaminhadas para a thread principal do Qt de forma segura.
- Em execuções **agendadas**, as etapas são logadas com o prefixo `Robô (agendado):`; em **reenvio offline** (se habilitado no código), `Robô (reenvio):`.

---

## Dados e arquivos locais

Pasta padrão (por usuário Windows):

`%AppData%\Roaming\MyworkPontoBot\`

| Arquivo | Conteúdo |
|---------|----------|
| `config.json` | URLs, seletores, perfis, eventos, flags |
| `logs.json` | Log da aplicação (inclui linhas `Robô: …`) |
| `history.json` | Histórico de batidas |
| `runtime_state.json` | Estado do agendador (execuções do dia, etc.) |

Credenciais ficam em arquivo separado gerido por `src/security.py` (DPAPI).

---

## Build do executável

```powershell
pyinstaller --noconfirm --onefile --windowed --name MyworkPontoBot main.py
```

Saída típica: `dist\MyworkPontoBot.exe`

---

## Observações legais e de uso

- Confirme com **RH / TI / compliance** da empresa se automação de ponto é permitida.
- O funcionamento depende de **seletores e URLs** alinhados ao site; atualizações do Mywork podem exigir ajustes.
- Este projeto é uma ferramenta de apoio; o uso é por sua conta e risco.

---

## Desenvolvimento rápido

```powershell
python -m py_compile main.py
python -m py_compile src\ui_main.py src\api_client.py src\scheduler_service.py
```

Para alterar o tempo limite das operações do robô na UI, edite `MainWindow._ROBOT_UI_TIMEOUT_MS` em `src/ui_main.py` (valor em **milissegundos**).
