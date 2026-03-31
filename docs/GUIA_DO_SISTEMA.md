# Guia do sistema — Mywork Ponto Bot

Este documento descreve **para que serve cada parte** da aplicação: telas, campos, botões e conceitos. Para instalação e pastas de dados, veja o [README principal](../README.md).

---

## 1. Visão geral

O **Mywork Ponto Bot** é um programa Windows que:

1. Abre o site **Mywork** num navegador controlado (**Chromium** via Playwright).
2. Faz **login** com e-mail e senha guardados localmente (protegidos).
3. Navega até a **página de ponto** e pode **registrar batidas** (entrada, pausa, retorno, saída).
4. **Agenda** batidas automáticas por dia da semana e horário.
5. Mantém **histórico** e **logs** das operações.

Componentes principais:

| Componente | Função |
|------------|--------|
| **Interface (Qt)** | Janela com abas, relógio, edição de configuração e agenda. |
| **AppController** | Liga interface, armazenamento, credenciais e agendador. |
| **MyworkApiClient** | Passo a passo no navegador (login, ponto, cliques, modal de motivo). |
| **SchedulerService** | Thread que, a cada ~20 s, verifica se algum evento agendado está no horário (com tolerância). |
| **Storage / Security** | Grava `config.json`, logs, histórico, estado; senha com DPAPI. |

---

## 2. Tela principal (acima das abas)

Estes elementos aparecem **sempre**, em qualquer aba selecionada.

### 2.1 Próximos agendamentos

- **O que é:** Lista dos **até 3 próximos** eventos futuros, somando perfis **ativos**.
- **Formato de cada linha:** data, hora, dia da semana, tipo de batida, nome do perfil entre colchetes; se o evento tiver descrição, ela aparece após um traço.
- **Para que serve:** Visão rápida do que o agendador vai disparar em seguida, sem abrir a aba Agendamentos.

### 2.2 Relógio (grande, à direita)

- **O que é:** Hora local no formato **HH:MM**, atualizada **a cada segundo**.
- **Para que serve:** Conferência visual da hora ao comparar com os horários agendados.

### 2.3 Status

- **O que é:** Uma linha de texto logo abaixo da área de agendamentos.
- **Exemplos:** “Agendador ativo”, “Credenciais não configuradas”, ou mensagens após notificações (ex.: ponto registrado).
- **Para que serve:** Estado resumido da aplicação e feedback recente.

---

## 3. Aba **Configuração**

Centraliza **acesso ao site** e **como o robô encontra os elementos** na página.

| Campo / controle | Para que serve |
|------------------|----------------|
| **E-mail** | Usuário usado no login do Mywork. É salvo em texto no fluxo de configuração; a **senha** vai para armazenamento protegido (DPAPI). |
| **Senha** | Senha do Mywork. Não fica em claro no `config.json`. |
| **URL de login** | Endereço da página onde o robô preenche e-mail/senha e clica em entrar (ex.: página inicial do app). |
| **URL da página de ponto** | Endereço onde o robô deve trabalhar para bater/registrar ponto. Se for só a raiz do app, o sistema pode normalizar para `/ponto` quando fizer sentido. |
| **Seletor campo e-mail** | Seletor CSS do campo de e-mail (ou equivalente) na tela de login. Usado primeiro na lista de estratégias do robô. |
| **Seletor campo senha** | Seletor CSS do campo de senha. |
| **Seletor botão login** | Seletor CSS do botão (ou elemento clicável) que envia o formulário de login. |
| **Seletor botão bater ponto** | Seletor base para ações de ponto; o robô também usa variações por tipo (entrada, pausa, etc.). |
| **Bloquear descrição repetida no site** | Se ativo, antes de registrar o robô compara a descrição que vai enviar com o **último comentário** visível no histórico da tela; se for igual (normalizado), **não** envia, para evitar duplicidade no portal. |
| **Tolerância (min)** | Janela em **minutos** ao redor do horário agendado: o agendador só tenta o ponto automático se a hora atual estiver dentro de `± tolerância` do horário do evento. Valor de 0 a 20 na interface. |
| **Iniciar com Windows** | Registra (ou remove) uma entrada em **Iniciar com o Windows** para abrir o app; costuma usar `--minimized` para ir direto à bandeja. |
| **Ocultar janela do navegador (headless)** | **Marcado:** o robô roda sem janela visível (segundo plano). **Desmarcado:** você vê o Chromium durante login, ponto e testes. |
| **Pausa com janela visível antes de fechar** | Segundos (0–120) de espera **no final** da operação antes de fechar o navegador, **somente** quando a janela está visível. Útil para conferir o resultado na tela. Com **0**, fecha assim que termina. **Ignorado** em modo headless (campo fica desabilitado). |
| **Testar login robô** | Salva a configuração atual, abre o navegador **visível**, executa login, abre a página de ponto e fecha. Serve para validar URLs e seletores. Durante a execução, a interface pode ir para a aba **Logs** e registrar **etapas**; há **limite de tempo** na UI (ver README). |
| **Salvar configuração** | Grava URLs, seletores, opções e perfis atuais no `config.json` e persiste e-mail/senha nos locais apropriados. |

**Observação:** Os textos padrão de descrição por tipo (`entrada`, `pausa`, etc.) continuam existindo **dentro do arquivo de configuração** para quando um evento de agenda **não** traz descrição própria; eles **não** são editados nesta aba.

---

## 4. Aba **Agendamentos**

Define **quando** e **com que descrição** o agendador tenta registrar cada batida.

### 4.1 Perfil ativo

- **O que é:** Caixa de seleção que liga ou desliga o perfil atual.
- **Para que serve:** Perfis desativados são ignorados na lista “Próximos agendamentos” e o agendador **não** executa os eventos deles.

### 4.2 Nome do perfil

- **O que é:** Nome legível (ex.: “Dias úteis”).
- **Para que serve:** Aparece nos próximos agendamentos e nos logs; ajuda a identificar o conjunto de regras.

### 4.3 Dias da semana (Seg … Dom)

- **O que é:** Marca em quais dias da semana os eventos deste perfil valem.
- **Convenção interna:** Segunda = 0, …, Domingo = 6.

### 4.4 Linha de novo evento: Hora, Tipo, Descrição

| Controle | Para que serve |
|----------|----------------|
| **Hora** | Horário no formato **HH:MM** do evento. |
| **Tipo** | Uma das batidas: `entrada`, `pausa`, `retorno`, `saida`. |
| **Descrição (opcional)** | Texto enviado ao site como motivo/comentário daquela batida. Se vazio, o robô usa o padrão interno do tipo. |
| **Adicionar evento** | Monta uma linha no editor abaixo e acrescenta ao texto da agenda. **Não** permite repetir o mesmo horário em dois eventos. |
| **Remover último** | Remove a última linha **não vazia** do editor. |
| **Remover linha atual** | Remove a linha onde está o cursor no editor de eventos. |

### 4.5 Editor “Eventos do perfil”

- **O que é:** Área de texto com **uma linha por evento**.
- **Formato:** `HH:MM tipo` ou `HH:MM tipo texto da descrição` (tudo após o segundo token é a descrição).
- **Para que serve:** Edição em massa, copiar/colar, ajuste fino. Ao **Salvar agendamentos**, o texto é validado (incluindo **horários únicos** no perfil).

### 4.6 Salvar agendamentos

- Grava o perfil (nome, ativo, dias, eventos) no `config.json`.
- Exige ao menos um dia marcado e ao menos um evento válido.

### 4.7 Teste de registro

- Executa **uma batida manual imediata** com o **Tipo** e a **Descrição** preenchidos na linha de evento (se a descrição estiver vazia, usa um texto de teste com data/hora).
- Útil para validar o fluxo completo sem esperar o horário agendado.
- Também muda para **Logs** e registra etapas, com o mesmo **limite de tempo** da UI que as outras operações longas do robô.

---

## 5. Aba **Histórico**

| Controle / área | Para que serve |
|-----------------|----------------|
| **Área de texto** | Lista linhas de cada tentativa de batida: data/hora, sucesso ou falha, tipo, origem (`manual`, `auto`, `retry`, etc.) e mensagem retornada. |
| **Atualizar histórico** | Recarrega o conteúdo do arquivo de histórico. |
| **Limpar histórico** | Apaga todo o histórico persistido (com confirmação). |

Diferente dos **Logs**, o histórico é focado em **registro de ponto** (sucesso/falha), não em mensagens técnicas gerais.

---

## 6. Aba **Logs**

| Controle / área | Para que serve |
|-----------------|----------------|
| **Área de texto** | Mensagens da aplicação: início do agendador, salvamentos, erros, e linhas **`Robô: …`** / **`Robô (agendado): …`** com as **etapas** da automação. |
| **Atualizar logs** | Recarrega do disco. |
| **Limpar logs** | Apaga o arquivo de logs (com confirmação). |

Durante **Testar login**, **Teste de registro** ou outras operações longas do robô iniciadas pela UI, o programa pode **mudar automaticamente** para esta aba para você acompanhar as etapas.

---

## 7. Bandeja do sistema (system tray)

| Ação | Efeito |
|------|--------|
| **Fechar** a janela principal (X) | A janela **esconde**; o app continua rodando e aparece um aviso de que está em segundo plano. |
| Menu do ícone → **Abrir** | Restaura a janela. |
| Menu do ícone → **Sair** | Encerra o agendador e fecha o aplicativo. |
| **Duplo clique** no ícone (quando suportado) | Mesmo efeito que Abrir. |

---

## 8. Agendador automático (em segundo plano)

- Roda numa **thread** separada, em ciclo com pausa de cerca de **20 segundos**.
- Para cada perfil **ativo**, no **dia da semana** certo, para cada **evento**:
  - Calcula se a hora atual está dentro da **tolerância** do horário do evento.
  - Evita repetir a mesma combinação **dia + perfil + tipo + horário** já executada com sucesso (estado em `runtime_state.json`).
  - Respeita **proteção contra batidas muito próximas** (evita duplicidade acidental).
- O fluxo de validação de batida é o mesmo do manual: a decisão final de sucesso/repetição é baseada no **histórico visível da página** (tabela "Histórico de pontos"), não em regra paralela exclusiva do agendador.
- Quando o clique acontece, mas não há confirmação imediata na tabela, o evento automático vira **pendente de confirmação**:
  - o agendador **não repete** a batida no mesmo evento (evita estourar limite diário por duplicidade);
  - agenda uma **verificação tardia** da tabela para confirmar se o registro apareceu depois.
- O intervalo dessa verificação tardia é `uncertain_confirmation_recheck_minutes` (padrão **30 minutos**).
- Em caso de falha, pode aplicar **espera** antes de nova tentativa automática naquele evento (conforme implementação em `scheduler_service.py`).

---

## 9. Modelo de dados (resumo)

| Conceito | Significado |
|----------|-------------|
| **AppConfig** | Todas as opções globais: URLs, seletores, flags, lista de perfis. |
| **ScheduleProfile** | Nome, ativo, dias da semana, lista de eventos. |
| **ScheduleEvent** | `time` (HH:MM), `punch_type`, `description` (opcional). |
| **PUNCH_TYPES** | Valores fixos: `entrada`, `pausa`, `retorno`, `saida`. |

---

## 10. Onde ajustar comportamento avançado

| Necessidade | Onde olhar |
|-------------|------------|
| Tempo máximo da operação do robô na UI (antes do aviso de timeout) | `MainWindow._ROBOT_UI_TIMEOUT_MS` em `src/ui_main.py` |
| Tempos de espera e textos de etapas do navegador | `src/api_client.py` |
| Intervalo do loop do agendador e regras de retry | `src/scheduler_service.py` |
| Caminhos dos arquivos JSON | `src/storage.py` |

---

*Documento alinhado ao comportamento esperado do código; se uma versão futura mudar a interface, atualize este guia junto.*
