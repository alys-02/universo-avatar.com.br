from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware

from sqlmodel import SQLModel, Field, Session, create_engine, select

from passlib.context import CryptContext


app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="universo-avatar-chave-secreta"
)


app.mount("/estilos", StaticFiles(directory="estilos"), name="estilos")
app.mount("/imagens", StaticFiles(directory="imagens"), name="imagens")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")
app.mount("/paginas", StaticFiles(directory="paginas"), name="paginas")
app.mount("/series", StaticFiles(directory="series"), name="series")
app.mount("/series_estilos", StaticFiles(directory="series_estilos"), name="series_estilos")


templates = Jinja2Templates(directory="templates")

senha_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


class Usuario(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nome_usuario: str = Field(unique=True, index=True)
    senha_hash: str


class Comentario(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    usuario_id: int
    nome: str
    texto: str
    data: datetime = Field(default_factory=datetime.now)


class Resposta(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    comentario_id: int
    usuario_id: int
    nome: str
    texto: str
    data: datetime = Field(default_factory=datetime.now)


class Reacao(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    comentario_id: int
    sessao_id: str
    tipo: str


engine = create_engine(
    "sqlite:///avatar.db",
    connect_args={"check_same_thread": False}
)

SQLModel.metadata.create_all(engine)


@app.get("/")
def inicio(request: Request):

    usuario_id = request.session.get("usuario_id")

    with Session(engine) as sessao:

        comentarios = sessao.exec(
            select(Comentario).order_by(Comentario.data.desc())
        ).all()

        dados_comentarios = []

        for comentario in comentarios:

            respostas = sessao.exec(
                select(Resposta)
                .where(Resposta.comentario_id == comentario.id)
                .order_by(Resposta.data.asc())
            ).all()

            sessao_id = request.session.get("sessao_id")

            if not sessao_id:
                sessao_id = str(uuid4())
                request.session["sessao_id"] = sessao_id

            reacoes = sessao.exec(
                select(Reacao)
                .where(Reacao.comentario_id == comentario.id)
            ).all()

            contagem = {
                "❤️": 0,
                "👍": 0,
                "😂": 0,
                "😮": 0,
                "😢": 0
            }

            minha_reacao = None

            for reacao in reacoes:

                if reacao.tipo in contagem:
                    contagem[reacao.tipo] += 1

                if reacao.sessao_id == sessao_id:
                    minha_reacao = reacao.tipo

            dados_comentarios.append({
                "comentario": comentario,
                "respostas": respostas,
                "reacoes": contagem,
                "minha_reacao": minha_reacao
            })

    usuario = None

    if usuario_id:

        with Session(engine) as sessao:

            usuario = sessao.get(
                Usuario,
                usuario_id
            )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "comentarios": dados_comentarios,
            "usuario": usuario
        }
    )


@app.get("/cadastro")
def cadastro(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="cadastro.html"
    )


@app.post("/cadastro")
def criar_conta(
    request: Request,
    nome_usuario: str = Form(...),
    senha: str = Form(...),
    confirmar_senha: str = Form(...)
):

    nome_usuario = nome_usuario.strip()

    if senha != confirmar_senha:

        return templates.TemplateResponse(
            request=request,
            name="cadastro.html",
            context={
                "erro": "As senhas não são iguais."
            }
        )

    if len(nome_usuario) < 3:

        return templates.TemplateResponse(
            request=request,
            name="cadastro.html",
            context={
                "erro": "O nome de usuário precisa ter pelo menos 3 caracteres."
            }
        )

    if len(senha) < 6:

        return templates.TemplateResponse(
            request=request,
            name="cadastro.html",
            context={
                "erro": "A senha precisa ter pelo menos 6 caracteres."
            }
        )

    with Session(engine) as sessao:

        usuario_existente = sessao.exec(
            select(Usuario)
            .where(Usuario.nome_usuario == nome_usuario)
        ).first()

        if usuario_existente:

            return templates.TemplateResponse(
                request=request,
                name="cadastro.html",
                context={
                    "erro": "Esse nome de usuário já existe."
                }
            )

        novo_usuario = Usuario(
            nome_usuario=nome_usuario,
            senha_hash=senha_context.hash(senha)
        )

        sessao.add(novo_usuario)
        sessao.commit()
        sessao.refresh(novo_usuario)

        request.session["usuario_id"] = novo_usuario.id

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.get("/login")
def login(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )


@app.post("/login")
def entrar(
    request: Request,
    nome_usuario: str = Form(...),
    senha: str = Form(...)
):

    nome_usuario = nome_usuario.strip()

    with Session(engine) as sessao:

        usuario = sessao.exec(
            select(Usuario)
            .where(Usuario.nome_usuario == nome_usuario)
        ).first()

        if not usuario or not senha_context.verify(
            senha,
            usuario.senha_hash
        ):

            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "erro": "Usuário ou senha incorretos."
                }
            )

        request.session["usuario_id"] = usuario.id

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.get("/logout")
def sair(request: Request):

    request.session.pop("usuario_id", None)

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.post("/comentarios")
def adicionar_comentario(
    request: Request,
    texto: str = Form(...)
):

    usuario_id = request.session.get("usuario_id")

    if not usuario_id:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    texto = texto.strip()

    if texto:

        with Session(engine) as sessao:

            usuario = sessao.get(
                Usuario,
                usuario_id
            )

            if usuario:

                comentario = Comentario(
                    usuario_id=usuario.id,
                    nome=usuario.nome_usuario,
                    texto=texto
                )

                sessao.add(comentario)
                sessao.commit()

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.post("/responder")
def responder_comentario(
    request: Request,
    comentario_id: int = Form(...),
    texto: str = Form(...)
):

    usuario_id = request.session.get("usuario_id")

    if not usuario_id:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    texto = texto.strip()

    if texto:

        with Session(engine) as sessao:

            usuario = sessao.get(
                Usuario,
                usuario_id
            )

            if usuario:

                resposta = Resposta(
                    comentario_id=comentario_id,
                    usuario_id=usuario.id,
                    nome=usuario.nome_usuario,
                    texto=texto
                )

                sessao.add(resposta)
                sessao.commit()

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.post("/reagir")
def reagir(
    request: Request,
    comentario_id: int = Form(...),
    tipo: str = Form(...)
):

    tipos_permitidos = {
        "❤️",
        "👍",
        "😂",
        "😮",
        "😢"
    }

    if tipo not in tipos_permitidos:

        return RedirectResponse(
            url="/",
            status_code=303
        )

    if "sessao_id" not in request.session:

        request.session["sessao_id"] = str(uuid4())

    sessao_id = request.session["sessao_id"]

    with Session(engine) as sessao:

        reacao = sessao.exec(
            select(Reacao)
            .where(
                Reacao.comentario_id == comentario_id,
                Reacao.sessao_id == sessao_id
            )
        ).first()

        if reacao:

            if reacao.tipo == tipo:

                sessao.delete(reacao)

            else:

                reacao.tipo = tipo
                sessao.add(reacao)

        else:

            nova_reacao = Reacao(
                comentario_id=comentario_id,
                sessao_id=sessao_id,
                tipo=tipo
            )

            sessao.add(nova_reacao)

        sessao.commit()

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.post("/apagar-comentario")
def apagar_comentario(
    request: Request,
    comentario_id: int = Form(...)
):

    usuario_id = request.session.get("usuario_id")

    if not usuario_id:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    with Session(engine) as sessao:

        comentario = sessao.get(
            Comentario,
            comentario_id
        )

        if comentario and comentario.usuario_id == usuario_id:

            respostas = sessao.exec(
                select(Resposta)
                .where(
                    Resposta.comentario_id == comentario_id
                )
            ).all()

            reacoes = sessao.exec(
                select(Reacao)
                .where(
                    Reacao.comentario_id == comentario_id
                )
            ).all()

            for resposta in respostas:
                sessao.delete(resposta)

            for reacao in reacoes:
                sessao.delete(reacao)

            sessao.delete(comentario)

            sessao.commit()

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.post("/apagar-resposta")
def apagar_resposta(
    request: Request,
    resposta_id: int = Form(...)
):

    usuario_id = request.session.get("usuario_id")

    if not usuario_id:

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    with Session(engine) as sessao:

        resposta = sessao.get(
            Resposta,
            resposta_id
        )

        if resposta and resposta.usuario_id == usuario_id:

            sessao.delete(resposta)
            sessao.commit()

    return RedirectResponse(
        url="/",
        status_code=303
    )