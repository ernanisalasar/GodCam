# GodCam

<!-- SPDX-License-Identifier: GPL-3.0-only -->

**Monitoramento desktop de câmeras IP XMEye/ONVIF em rede local.**

<sub>Versão 0.0.1 · Em desenvolvimento</sub>

> [!IMPORTANT]
> **PROJETO EM ATUALIZAÇÃO**
>
> O GodCam está em estágio inicial de desenvolvimento (versão 0.0.1). Este projeto receberá atualizações frequentes e poderá conter erros, funcionalidades experimentais, informações incompletas ou documentação desatualizada.
>
> A estrutura, as funcionalidades e os procedimentos descritos neste README ainda estão sujeitos a alterações. Não considere esta versão uma distribuição estável ou definitiva.

## Sobre o projeto

GodCam é uma aplicação desktop desenvolvida em Python e PyQt6 para monitoramento de câmeras IP, com suporte a equipamentos XMEye e comunicação ONVIF.

A aplicação oferece visualização multicâmera, controles PTZ, reprodução de áudio, comunicação por microfone e gravação de vídeo.

O projeto utiliza interface em tema escuro e possui mecanismos de reconexão automática e acompanhamento do estado de reprodução.

## Tecnologias utilizadas

- Python
- PyQt6
- libVLC
- ONVIF
- RTSP
- DVRIP (comunicação experimental)
- FFmpeg (gravação de vídeo)

## Estrutura do projeto

```text
godcam/
├── main.py
├── requirements.txt
├── README.md
└── godcam/
    ├── config.py
    ├── core/
    │   ├── network.py
    │   ├── rtsp.py
    │   ├── player.py
    │   ├── ptz.py
    │   ├── talk.py
    │   └── recorder.py
    ├── resources/
    │   ├── icons/
    │   ├── scan-eye.svg
    │   └── scan-eye.ico
    └── ui/
        ├── theme.py
        ├── main_window.py
        ├── video_tile.py
        ├── control_panel.py
        ├── camera_dialog.py
        └── help_dialog.py
```

### Principais módulos

| Arquivo | Responsabilidade |
|---|---|
| `main.py` | Ponto de entrada da aplicação |
| `config.py` | Modelo CameraConfig e armazenamento das câmeras |
| `core/network.py` | Detecção de conectividade local ou externa |
| `core/rtsp.py` | Montagem das URLs RTSP |
| `core/player.py` | Reprodução de vídeo e áudio utilizando libVLC |
| `core/ptz.py` | Movimentação ONVIF ContinuousMove/Stop em thread própria |
| `core/talk.py` | Microfone, codificação G.711 e transporte DVRIP experimental |
| `core/recorder.py` | Gravação de vídeo MP4 utilizando FFmpeg |
| `ui/main_window.py` | Janela principal, grade e orquestração |
| `ui/video_tile.py` | Reprodução de cada câmera e reconexão automática |
| `ui/control_panel.py` | Controles PTZ, volume, microfone e gravação |
| `ui/theme.py` | Tema escuro e estilos da aplicação |
| `ui/camera_dialog.py` | Cadastro e edição de câmeras |
| `ui/help_dialog.py` | Documentação e ajuda offline |

## Instalação | Windows

### Requisitos

- Windows 10 ou superior.
- Python 3.10 ou superior, 64 bits.
- VLC Desktop 64 bits.
- FFmpeg, necessário para a funcionalidade de gravação.

### Instalação das dependências

Instale o VLC Desktop pelo site oficial:

https://www.videolan.org/vlc/

Instale o FFmpeg:

```powershell
winget install Gyan.FFmpeg
```

Instale as dependências Python:

```powershell
pip install -r requirements.txt
```

Execute a aplicação:

```powershell
python main.py
```

## Configuração das câmeras

Na primeira execução, o projeto inicia sem câmeras cadastradas. Cadastre manualmente apenas os equipamentos que pertencem à sua rede.

Edite cada câmera pela interface e informe os dados correspondentes ao equipamento:

- Nome da câmera.
- Endereço IP ou hostname.
- Usuário.
- Senha.
- Modelo da URL RTSP.
- Portas de comunicação.

**Importante:** os endereços e as credenciais devem corresponder à sua rede e aos seus equipamentos.

As configurações são armazenadas em:

```text
%APPDATA%\godcam\cameras.json
```

## Se o vídeo não abrir

Primeiro, teste a URL RTSP diretamente no VLC Desktop:

**Mídia → Abrir fluxo de rede.**

Exemplo de formato de URL:

```text
rtsp://<IP_DA_CAMERA>:554/user=<USUARIO>&password=<SENHA>&channel=1&stream=0.sdp?real_stream
```

Caso não funcione, tente alterar o campo "Modelo da URL RTSP" na configuração da câmera.

Um exemplo alternativo é:

```text
rtsp://{host}:{port}/onvif1
```

Verifique também as portas de comunicação do equipamento. As portas frequentemente utilizadas incluem RTSP 554, ONVIF 8899 e HTTP 80, mas podem variar conforme o fabricante e o firmware.

### Problemas de autenticação PTZ

Quando houver erro de autenticação nos comandos ONVIF, verifique o relógio interno da câmera.

O projeto possui compensação de horário através do parâmetro `adjust_time`.

## Falar | Push-to-talk experimental

A funcionalidade Falar utiliza captura do microfone e codificação G.711 A-law.

O transporte de áudio até a câmera utiliza o protocolo proprietário DVRIP, pela porta 34567.

**Esta funcionalidade é experimental.** O funcionamento depende do firmware e da implementação do protocolo utilizada pelo equipamento. Não há garantia de compatibilidade com todas as câmeras.

Para investigar problemas de comunicação, pode-se utilizar o Wireshark com o filtro:

```text
tcp.port == 34567
```

Compare a comunicação com o funcionamento do botão Falar no XMEye VMS.

Os ajustes específicos do transporte devem ser concentrados na classe `DvripTalkTransport`, localizada em:

```text
godcam/core/talk.py
```

Câmeras que ofereçam um canal de retorno de áudio ONVIF/RTSP compatível poderão exigir uma implementação adicional de `TalkTransport`, utilizando RTSP e RTP.

## Acesso remoto

### Opção A | Tailscale (recomendada)

A utilização do Tailscale com um subnet router permite acessar as câmeras remotamente sem precisar expor diretamente suas portas à internet.

As câmeras não precisam executar o Tailscale. Pode-se utilizar um computador ou Raspberry Pi permanentemente conectado à rede local.

Procedimento geral:

1. Instale o Tailscale no computador que funcionará como subnet router.
2. Instale o Tailscale nos dispositivos que utilizarão o GodCam remotamente.
3. No computador da rede local, anuncie a sub-rede:

```powershell
tailscale up --advertise-routes=192.0.2.0/24
```

`192.0.2.0/24` é um exemplo reservado para documentação. Substitua-o pela sub-rede efetivamente utilizada na sua rede.

4. Acesse o painel administrativo do Tailscale.
5. Em Machines, abra as configurações de rotas e aprove a rota anunciada.
6. Com o Tailscale conectado fora de casa, utilize os endereços locais das câmeras através da rota autorizada.

O GodCam pode usar o endereço local ou externo cadastrado, mas não configura Tailscale, DDNS, VPN, roteador ou encaminhamento de portas. Essas instruções são apenas orientação de infraestrutura e devem ser avaliadas pelo administrador da rede.

**Atenção:** se a rede externa também utilizar a mesma sub-rede da sua rede doméstica, poderá ocorrer conflito de endereçamento.

Recomenda-se reservar endereços IP fixos para as câmeras através do DHCP do roteador.

Para economizar banda, pode-se utilizar o stream secundário (Stream = 1), quando suportado pelo equipamento.

### Opção B | Port forwarding e DDNS

Outra possibilidade é utilizar encaminhamento de portas no roteador e um serviço DDNS.

Procedimento geral:

1. Reserve endereços IP fixos para as câmeras.
2. Configure um hostname em um serviço DDNS, como No-IP ou DuckDNS.
3. Configure o encaminhamento das portas externas para os serviços das câmeras.
4. Prefira portas externas diferentes das portas padrão.
5. No GodCam, informe o endereço DDNS e as respectivas portas externas.

**Riscos de segurança:**

Equipamentos com firmwares XMEye/Xiongmai possuem histórico de vulnerabilidades de segurança.

Recomendações:

- Troque as senhas padrão.
- Desative serviços P2P/nuvem que não sejam necessários.
- Evite expor serviços de câmeras diretamente à internet.
- Restrinja o acesso remoto sempre que possível.

A opção Tailscale é preferível quando disponível.

**CGNAT:** algumas operadoras utilizam CGNAT, o que pode impedir o funcionamento de encaminhamento de portas. Nesse cenário, solicite um endereço IP público à operadora ou utilize uma solução como Tailscale.

## Monitoramento multicâmera

O GodCam oferece uma grade configurável com os seguintes layouts:

- 1×1
- 2×2
- 2×3
- 3×3
- 4×4
- 5×5
- 6×6
- 8×8

### Organização dos vídeos

- Os blocos utilizam proporção 16:9 como referência.
- A janela inicial considera a área útil do monitor.
- Os controles podem ser rolados verticalmente.
- O modo padrão de exibição é Preencher.
- O modo Ajustar mantém o enquadramento completo.
- O modo Esticar pode deformar a imagem.

Em fontes 16:9, o modo Preencher ocupa o bloco sem corte.

O cabeçalho do bloco fica sobreposto ao vídeo e não reduz a área de reprodução.

### Seleção e movimentação

- Conecte uma câmera pelo botão correspondente ou com duplo clique na lista.
- A câmera conectada ocupa o próximo bloco livre.
- Selecione uma câmera conectada e clique em outro bloco para movê-la.
- A troca de layout preserva os players.
- As atribuições fora dos blocos visíveis reaparecem quando a grade é ampliada.

### Maximização dos vídeos

O duplo clique em um bloco de vídeo permite ampliar e restaurar sua visualização.

Apenas a câmera ativa, identificada pela borda azul, reproduz áudio, utilizando uma conexão RTSP dedicada.

### Estados de reprodução

A aplicação acompanha a progressão dos quadros exibidos pelo libVLC para determinar o estado de cada câmera.

Os estados disponíveis incluem:

- DESCONECTADA
- CONECTANDO
- REPRODUZINDO
- SEM VÍDEO
- VÍDEO CONGELADO
- ERRO
- RECONECTANDO

Uma porta RTSP acessível, por si só, não significa que exista vídeo sendo reproduzido.

O estado REPRODUZINDO exige progressão dos contadores de quadros exibidos pelo libVLC.

Quando não há novos quadros, a aplicação pode indicar SEM VÍDEO ou VÍDEO CONGELADO e iniciar o processo de reconexão progressiva.

## Interface e recursos visuais

A aplicação utiliza tema escuro, com identidade visual própria.

Os ícones utilizados na interface são provenientes do projeto Lucide/Feather e possuem seus respectivos avisos de licença em:

```text
godcam/resources/icons/LICENSE.txt
```

O ícone da aplicação também é derivado do Lucide e está disponível em:

```text
godcam/resources/scan-eye.svg
godcam/resources/scan-eye.ico
```

O menu Ajuda disponibiliza documentação offline, enquanto a opção Sobre apresenta a identidade do aplicativo.

## Segurança e armazenamento

As senhas das câmeras são protegidas com a DPAPI do Windows, vinculadas ao usuário Windows que as cadastrou. O conteúdo protegido é armazenado no arquivo:

```text
%APPDATA%\godcam\cameras.json
```

O arquivo não contém a senha em texto puro. Se ele for transferido para outro usuário Windows ou outra instalação, será necessário informar a senha novamente.

**Cuidados importantes:**

- Não compartilhe seu `cameras.json`.
- Não publique credenciais, tokens ou certificados.
- Não inclua configurações privadas no repositório.
- Não utilize senhas reais em exemplos, capturas de tela ou documentação pública.
- Evite compartilhar mensagens de erro sem revisar os dados de rede exibidos.

## Licença e autoria

Este projeto é distribuído sob a [GNU General Public License v3.0 only](LICENSE) (`GPL-3.0-only`). Consulte também [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) para os avisos de componentes de terceiros.

Desenvolvido por Ernani Salasar.

## Estado do desenvolvimento

**Versão 0.0.1 Em desenvolvimento.**

O GodCam ainda está recebendo melhorias e correções.

A estabilidade e a compatibilidade das funcionalidades podem variar conforme o modelo da câmera, o firmware, os protocolos utilizados e o ambiente Windows.

Este README será atualizado conforme a evolução do projeto.

Problemas, limitações e funcionalidades experimentais poderão ser revisados nas próximas versões.
