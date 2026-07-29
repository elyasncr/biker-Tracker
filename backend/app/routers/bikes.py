from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Activity, Bike
from ..services import bikes as bike_service
from ..services import drivetrain

router = APIRouter(prefix="/api/bikes", tags=["bikes"])


class BikeInput(BaseModel):
    """Corpo do POST: cria uma bike. So o nome e obrigatorio."""

    name: str
    crr: float | None = None
    cda: float | None = None
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    kind: str = "speed"
    weight_kg: float | None = None
    wheel_circumference_mm: int | None = None
    chainrings: list[int] | None = None
    cassette: list[int] | None = None
    notes: str | None = None
    is_default: bool = False

    @field_validator("chainrings")
    @classmethod
    def _coroas_validas(cls, v):
        if v is not None and not all(20 <= d <= 60 for d in v):
            raise ValueError("Coroa fora da faixa útil (20 a 60 dentes)")
        return sorted(v, reverse=True) if v else v

    @field_validator("cassette")
    @classmethod
    def _cogs_validos(cls, v):
        if v is not None and not all(9 <= d <= 52 for d in v):
            raise ValueError("Cog fora da faixa útil (9 a 52 dentes)")
        return sorted(v) if v else v

    @field_validator("wheel_circumference_mm")
    @classmethod
    def _aro_valido(cls, v):
        # Faixa util: 1000 mm cobre roda de 16", 2400 cobre 29" com pneu gordo.
        # Fora disso o mapa de marchas inteiro sai deslocado, sem aviso nenhum.
        if v is not None and not 1000 <= v <= 2400:
            raise ValueError("Circunferência fora da faixa útil (1000 a 2400 mm)")
        return v


class BikeUpdate(BikeInput):
    """Corpo do PATCH: TUDO opcional.

    Sem isso o PATCH se comporta como PUT - manda so a catraca e apaga marca,
    modelo, ano, peso e aro, porque todo campo ausente vira None e o setattr
    grava esse None por cima. Quem edita um campo nao espera perder os outros.
    """

    name: str | None = None
    kind: str | None = None
    is_default: bool | None = None


@router.get("")
def list_bikes(db: Session = Depends(get_db)):
    result = []
    for bike in db.scalars(select(Bike).order_by(Bike.name)):
        result.append(
            {
                "id": bike.id,
                "name": bike.name,
                "brand": bike.brand,
                "model": bike.model,
                "year": bike.year,
                "kind": bike.kind,
                "weight_kg": bike.weight_kg,
                "wheel_circumference_mm": bike.wheel_circumference_mm,
                "chainrings": bike.chainrings,
                "cassette": bike.cassette,
                "notes": bike.notes,
                "is_default": bike.is_default,
                "signatures": bike.signatures or [],
                "stats": bike_service.bike_stats(db, bike),
            }
        )
    return result


@router.get("/drivetrain-presets")
def drivetrain_presets():
    """Catalogo de coroas, catracas e aros para o formulario da Garagem."""
    return drivetrain.PRESETS


@router.post("", status_code=201)
def create_bike(payload: BikeInput, db: Session = Depends(get_db)):
    bike = Bike(**payload.model_dump(), signatures=[])
    if bike.is_default:
        for other in db.scalars(select(Bike).where(Bike.is_default.is_(True))):
            other.is_default = False
    db.add(bike)
    db.commit()
    db.refresh(bike)
    return {"id": bike.id, "name": bike.name}


@router.patch("/{bike_id}")
def update_bike(bike_id: int, payload: BikeUpdate, db: Session = Depends(get_db)):
    bike = db.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(404, "Bike não encontrada")

    # exclude_unset e o coracao do conserto: so grava o que o cliente REALMENTE
    # mandou. Sem ele, todo campo ausente vira None e o setattr apaga o que ja
    # estava la - mandar so a catraca zerava marca, modelo, ano, peso e aro.
    dados = payload.model_dump(exclude_unset=True)

    if dados.get("is_default"):
        for other in db.scalars(select(Bike).where(Bike.is_default.is_(True), Bike.id != bike_id)):
            other.is_default = False

    for key, value in dados.items():
        setattr(bike, key, value)

    db.commit()
    return {"id": bike.id, "name": bike.name}


@router.delete("/{bike_id}", status_code=204)
def delete_bike(bike_id: int, db: Session = Depends(get_db)):
    bike = db.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(404, "Bike não encontrada")
    for ride in db.scalars(select(Activity).where(Activity.bike_id == bike_id)):
        ride.bike_id = None
    db.delete(bike)
    db.commit()


@router.post("/{bike_id}/claim/{activity_id}")
def claim_activity(bike_id: int, activity_id: int, db: Session = Depends(get_db)):
    """Voce diz uma vez que esse pedal foi nesta bike; o sistema aprende os sensores.

    Todos os outros treinos com a mesma assinatura de sensores sao adotados junto,
    inclusive os antigos.
    """
    bike = db.get(Bike, bike_id)
    activity = db.get(Activity, activity_id)
    if bike is None or activity is None:
        raise HTTPException(404, "Bike ou treino não encontrado")

    adopted, conflict = bike_service.assign_and_learn(db, activity, bike)

    if conflict:
        message = (
            f"Treino atribuído a {bike.name}. Esses mesmos sensores já pertencem a outra bike, então eles "
            f"viajam entre as duas — a detecção automática foi desligada para eles. Use a atribuição por "
            f"período para os próximos, que resolve vários de uma vez."
        )
    elif adopted:
        message = f"{adopted} treino(s) com os mesmos sensores também foram atribuídos a {bike.name}."
    elif activity.sensor_signature:
        message = f"Treino atribuído a {bike.name}."
    else:
        message = (
            f"Treino atribuído a {bike.name}. Esse .fit não trouxe sensores, então não há como reconhecer "
            f"sozinho — marque uma bike como padrão se a maioria dos pedais for nela."
        )

    return {
        "bike": bike.name,
        "activity_id": activity_id,
        "also_assigned": adopted,
        "conflict": conflict,
        "signature": activity.sensor_signature,
        "message": message,
    }


@router.post("/{bike_id}/assign-range")
def assign_range(bike_id: int, start: datetime, end: datetime, db: Session = Depends(get_db)):
    """Atribui todos os treinos de um periodo a uma bike."""
    bike = db.get(Bike, bike_id)
    if bike is None:
        raise HTTPException(404, "Bike não encontrada")
    count = bike_service.assign_range(db, bike, start, end)
    return {"assigned": count, "message": f"{count} treino(s) atribuído(s) a {bike.name}."}


@router.get("/unassigned")
def unassigned(db: Session = Depends(get_db)):
    """Treinos sem bike, agrupados por assinatura: um clique resolve o grupo inteiro."""
    rides = db.scalars(select(Activity).where(Activity.bike_id.is_(None)).order_by(Activity.started_at.desc()))
    groups: dict[str, dict] = {}
    for ride in rides:
        key = ride.sensor_signature or "sem-sensores"
        group = groups.setdefault(
            key,
            {"signature": ride.sensor_signature, "count": 0, "sample_activity_id": ride.id, "rides": []},
        )
        group["count"] += 1
        if len(group["rides"]) < 5:
            group["rides"].append(
                {"id": ride.id, "title": ride.title, "date": ride.started_at.date().isoformat()}
            )
    return list(groups.values())
