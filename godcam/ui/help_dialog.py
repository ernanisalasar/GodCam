"""Offline help and application information."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QTabWidget, QTextBrowser, QVBoxLayout, QWidget


_HELP_HTML = """
<h1>Ajuda do GodCam</h1>
<p>GodCam é um software de monitoramento de câmeras IP em rede local. Esta ajuda funciona offline.</p>

<h2>Primeiros passos</h2>
<p>Cadastre uma câmera com <b>Adicionar câmera</b>, informe seu endereço e os dados de
acesso, selecione-a e use <b>Conectar</b>. Conexão TCP com a porta RTSP não comprova
que o dispositivo autenticou, negociou o fluxo ou está entregando quadros de vídeo.</p>

<h2>Cadastro e gerenciamento</h2>
<p>O cadastro manual aceita nome, IP local, endereço externo opcional, portas RTSP,
ONVIF e DVRIP, portas externas, usuário, senha, canal, stream, preferência de conexão
e modelo da URL RTSP. Não inclua credenciais em exemplos ou mensagens compartilhadas.
Use <b>Editar câmera</b> para atualizar os dados e <b>Remover câmera</b> para excluí-la
do cadastro. Os botões Conectar, Desconectar e Conectar todas ficam no painel esquerdo.
As configurações são armazenadas em <code>%APPDATA%\\godcam\\cameras.json</code>.</p>

<h2>Grade de monitoramento</h2>
<p>Escolha 1×1, 2×2, 2×3, 3×3, 4×4, 5×5, 6×6 ou 8×8. Clique em um bloco ocupado para
selecionar sua câmera; selecione uma câmera e clique em outro bloco para movê-la.
Duplo clique no vídeo amplia; duplo clique novamente restaura a grade. Alterar a grade
reorganiza os tiles sem recriar os players. Blocos sem câmera permanecem vazios.</p>
<p>Preencher é o modo padrão. Ajustar prioriza o quadro completo e Esticar pode deformar
a proporção. O resultado depende da política de aspecto aceita pela saída nativa do VLC.</p>

<h2>Áudio e PTZ</h2>
<p>O áudio da câmera ativa usa uma conexão RTSP dedicada; os tiles de vídeo permanecem
independentes. Ajuste o volume ou marque Mudo. Os controles PTZ
movem a câmera enquanto o botão direcional estiver pressionado; solte ou use Parar para
interromper. Zoom e velocidade dependem do suporte do dispositivo e do firmware ONVIF.</p>

<h2>Gravação e push-to-talk</h2>
<p>Selecione uma câmera reproduzindo e use Gravar para iniciar ou interromper a captura.
O gravador requer o executável <code>ffmpeg</code> disponível no PATH. Os arquivos são
salvos em <code>Vídeos\\godcam</code>. Push-to-talk usa captura de microfone e transporte
DVRIP experimental; sua disponibilidade depende do firmware e não é garantida em todos
os modelos.</p>

<h2>Solução de problemas</h2>
<ul>
<li><b>Sem conexão:</b> confira IP, porta, rota local e se o dispositivo está acessível.</li>
<li><b>Tela preta/branca ou sem vídeo:</b> confirme caminho RTSP, canal, stream e codec.
Uma porta aberta, resposta OPTIONS ou estado Playing não provam que quadros estão sendo
exibidos; observe o estado do tile e a progressão de vídeo.</li>
<li><b>Autenticação:</b> confira usuário e senha cadastrados. Não os envie em capturas,
logs ou mensagens.</li>
<li><b>Reconexão:</b> o aplicativo tenta novamente com espera progressiva. Se persistir,
verifique o dispositivo e a rede local.</li>
<li><b>Áudio:</b> confirme se a transmissão inclui áudio; ajuste o volume e o estado de mudo.</li>
<li><b>PTZ:</b> confirme compatibilidade ONVIF, perfil PTZ e permissões da conta.</li>
<li><b>Gravação:</b> confirme que FFmpeg está instalado e acessível no PATH.</li>
</ul>
<p>Antes de compartilhar uma captura Wireshark, remova usuários, senhas, tokens e URLs
que possam conter credenciais.</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None, show_about: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajuda do GodCam" if not show_about else "Sobre o GodCam")
        self.setWindowIcon(QIcon(str(Path(__file__).parent.parent / "resources" / "scan-eye.ico")))
        self.resize(760, 640)

        tabs = QTabWidget(self)
        help_text = QTextBrowser(tabs)
        help_text.setOpenExternalLinks(False)
        help_text.setHtml(_HELP_HTML)
        tabs.addTab(help_text, "Ajuda")

        about = QWidget(tabs)
        about_layout = QVBoxLayout(about)
        about_layout.setContentsMargins(32, 32, 32, 32)
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(self.windowIcon().pixmap(96, 96))
        about_layout.addWidget(logo)
        name = QLabel("<h1>GodCam</h1><p>GodCam — Monitoramento de câmeras IP em rede local.</p>"
                      "<p><b>Desenvolvido por Ernani Salasar.</b></p>"
                      "<p>Versão: não definida no projeto.</p>"
                      "<p>Tecnologias: Python, PyQt6, libVLC, RTSP e ONVIF.</p>"
                      "<p>Ícone scan-eye do Lucide (licença ISC).</p>")
        name.setWordWrap(True)
        name.setTextFormat(Qt.TextFormat.RichText)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)
        about_layout.addStretch(1)
        tabs.addTab(about, "Sobre")
        tabs.setCurrentIndex(1 if show_about else 0)

        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(close_button)
