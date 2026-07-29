from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Activity(Base):
    """Um treino. Uma linha por arquivo .fit (ou por atividade vinda da API)."""

    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("file_hash", name="uq_activity_file_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # Origem
    source: Mapped[str] = mapped_column(String(16), default="fit")  # fit | igpsport
    external_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)

    # Identificacao
    # Hora LOCAL do pedal, tirada do proprio .fit (timestamp vs local_timestamp
    # da mensagem `activity`). Guardar UTC aqui fazia um pedal das 18:22 aparecer
    # como 21:22 na tela, e jogava um pedal noturno para o dia seguinte.
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sport: Mapped[str] = mapped_column(String(32), default="cycling")
    device: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Resumo
    duration_s: Mapped[float] = mapped_column(Float, default=0)
    moving_time_s: Mapped[float] = mapped_column(Float, default=0)
    distance_km: Mapped[float] = mapped_column(Float, default=0)
    elevation_gain_m: Mapped[float] = mapped_column(Float, default=0)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)

    avg_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_cadence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Espelham o que o app do iGPSPORT mostra na tela de resumo
    descent_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_up_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_up_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_down_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade_down_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vam_up_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    vam_up_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Potencia veio de potenciometro ou foi calculada pela fisica?
    power_is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metricas derivadas
    normalized_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    variability_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    trimp: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Curva de potencia da propria atividade: {"5": 780, "60": 410, ...}
    power_curve: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hr_zones_s: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    power_zones_s: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Qual bike foi usada, e a impressao digital dos sensores que provou isso
    bike_id: Mapped[int | None] = mapped_column(ForeignKey("bikes.id"), nullable=True)
    sensors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sensor_signature: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)

    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bike: Mapped["Bike | None"] = relationship(back_populates="activities")
    stream: Mapped["ActivityStream"] = relationship(
        back_populates="activity", cascade="all, delete-orphan", uselist=False
    )


class Bike(Base):
    """Uma bike do seu quartinho.

    A identificacao acontece pelos sensores: cadencia, velocidade e potenciometro
    ficam parafusados numa bike so e cada um tem um numero de radio unico gravado
    no .fit. Voce nomeia a bike uma vez e o sistema reconhece sozinho dai em diante.
    """

    __tablename__ = "bikes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    brand: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="speed")  # speed | mtb | gravel | urbana
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Coeficientes do modelo de potencia. Vazio usa o padrao do tipo de bike.
    crr: Mapped[float | None] = mapped_column(Float, nullable=True)
    cda: Mapped[float | None] = mapped_column(Float, nullable=True)
    wheel_circumference_mm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Transmissao declarada. Guardamos a LISTA DE DENTES, nao o nome do preset:
    # duas fontes de verdade acabam divergindo, e e a lista que entra na conta.
    chainrings: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [42, 34, 24]
    cassette: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [14, 16, ..., 34]
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assinaturas de sensores ja vistas nesta bike (uma bike pode ganhar sensor novo)
    signatures: Mapped[list | None] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    activities: Mapped[list["Activity"]] = relationship(back_populates="bike")


class ActivityStream(Base):
    """Serie temporal comprimida do treino, guardada como JSON para o grafico de detalhe."""

    __tablename__ = "activity_streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id", ondelete="CASCADE"))

    # Cada campo e uma lista de valores alinhada por indice (amostrada a cada N segundos)
    payload: Mapped[dict] = mapped_column(JSON)

    activity: Mapped[Activity] = relationship(back_populates="stream")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(16), default="fit")
    imported: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class OAuthToken(Base):
    """Guarda o token da iGPSPORT Open Platform quando/se voce tiver acesso."""

    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), unique=True, default="igpsport")
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)


class WeightEntry(Base):
    """Peso do ciclista ao longo do tempo.

    Existe por dois motivos. O primeiro e obvio: metade do objetivo do usuario e
    perder peso, e sem serie nao ha tendencia. O segundo e silencioso e talvez
    mais importante: o modelo de potencia usa a massa total na conta da fisica, e
    hoje ele le um valor fixo do .env. Quem emagrece 8 kg segue tendo a potencia
    calculada com o corpo antigo, e a comparacao entre meses fica contaminada.
    """

    __tablename__ = "weight_entries"
    __table_args__ = (UniqueConstraint("measured_on", name="uq_weight_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Um lancamento por dia. Relancar o mesmo dia sobrescreve, senao tres
    # pesagens da mesma manha brigam pela linha de tendencia.
    measured_on: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CoachGoal(Base):
    """A meta de constancia, declarada pelo usuario. Linha unica (id=1).

    O treinador pode SUGERIR uma meta maior, mas quem altera e o usuario - e a
    sugestao e limitada a +10% da media de 4 semanas e desligada depois de uma
    semana abaixo da meta. Ver as regras R2 e R3 do spec.
    """

    __tablename__ = "coach_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    rides_per_week: Mapped[int] = mapped_column(Integer, default=3)
    minutes_per_week: Mapped[int] = mapped_column(Integer, default=180)
    target_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
