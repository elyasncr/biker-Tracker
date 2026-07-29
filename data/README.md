# data/

Solte aqui os arquivos `.fit` exportados do app iGPSPORT. Subpastas funcionam.

No app: abra o treino → menu de compartilhar/exportar → escolha o formato `.fit`.

Depois é só clicar em "Ler pasta data/" na interface, ou chamar `POST /api/sync`.
Reimportar o mesmo arquivo não gera duplicata — cada treino é identificado pelo
hash SHA-256 do arquivo.
