# Deploy do Smart Shopper na Streamlit Community Cloud

Subir o app na **Streamlit Community Cloud** (gratuita) para ter um endereço público e usar em cadastros (ex.: chave API AliExpress). Depois do deploy, dá para ir aperfeiçoando em cima do mesmo repositório.

---

## Checklist rápido (subir agora)

- [ ] Criar repositório no GitHub (se ainda não tiver)
- [ ] Garantir que `.gitignore` existe (secrets e `.data/` não vão pro repositório)
- [ ] Fazer push do código (sem o arquivo `secrets.toml` — ele fica só na sua máquina)
- [ ] Em [share.streamlit.io](https://share.streamlit.io/) → New app → preencher repositório, **Main file path**: `smart_shopper/app.py`, **App root directory**: `smart_shopper`
- [ ] Depois do deploy, em Settings → Secrets colar as chaves (GROQ, etc.) em TOML
- [ ] Usar a URL do app onde pedirem (ex.: AliExpress)

## Pré-requisitos

1. **Conta no GitHub** – o código precisa estar em um repositório (público ou privado).
2. **Conta na [Streamlit Community Cloud](https://share.streamlit.io/)** – login com GitHub.

## Passo a passo

### 1. Subir o código no GitHub

Se ainda não tiver:

```bash
cd c:\sistemafiliados
git init
git add .
git commit -m "Smart Shopper - app para deploy"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/sistemafiliados.git
git push -u origin main
```

(Substitua `SEU_USUARIO/sistemafiliados` pelo seu usuário e nome do repositório.)

### 2. Deploy na Streamlit Cloud

1. Acesse **[share.streamlit.io](https://share.streamlit.io/)** e faça login com GitHub.
2. Clique em **"New app"**.
3. Preencha:
   - **Repository**: `SEU_USUARIO/sistemafiliados`
   - **Branch**: `main`
   - **Main file path**: `smart_shopper/app.py`
   - **App root directory**: `smart_shopper`  
     (assim o `requirements.txt` e o `core` ficam corretos.)
4. Clique em **"Deploy"**.

O app será construído e você receberá um link do tipo:

`https://SEU-APP-NOME.streamlit.app`

### 3. Configurar secrets (API keys) na nuvem

As chaves **não** devem ir no código. Na Streamlit Cloud:

1. No dashboard do app, abra **"Settings"** → **"Secrets"**.
2. Cole o conteúdo no formato TOML, por exemplo:

```toml
GROQ_API_KEY = "sua-chave-groq"
GEMINI_API_KEY = "sua-chave-gemini"
HF_TOKEN = "sua-chave-huggingface"
SERPAPI_KEY = "sua-chave-serpapi"
AMAZON_TAG = "sua-tag-amazon"
ALIEXPRESS_ADMITAD_CAMPAIGN_CODE = "seu-codigo-admitad"
```

Salve. O app passará a usar esses valores como `st.secrets`.

### 4. Usar o endereço do app (ex.: AliExpress)

Com o app no ar, você tem uma URL pública estável, por exemplo:

`https://seu-smart-shopper.streamlit.app`

Use essa URL onde a AliExpress (ou outro programa de afiliados) pedir **URL do site/aplicação** ou **domínio** para liberar a chave API ou o cadastro de afiliado.

---

## Observações

- **Modo gratuito**: o app roda em modo gratuito (sem SerpApi = sem preços ao vivo; sem chaves de IA = refinamento determinístico). Para preços ao vivo e IA, configure as chaves em **Secrets**.
- **Repositório privado**: a Streamlit Cloud permite app a partir de repo privado; na conta gratuita há limites de uso.
- **Secrets**: nunca faça commit de `secrets.toml` ou de chaves no repositório. Use apenas **Secrets** no dashboard da Streamlit Cloud.

Se quiser, na próxima mensagem podemos revisar o `requirements.txt` ou a pasta `smart_shopper` para garantir que nada quebre no deploy.
