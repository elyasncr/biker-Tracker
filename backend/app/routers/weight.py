"""Peso do ciclista. Fora do namespace do treinador de proposito: e dado do
atleta, alimenta o modelo de potencia, e sobrevive a aba que o exibe."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WeightEntry

router = APIRouter(prefix="/api/weight", tags=["peso"])


class WeightInput(BaseModel):
    measured_on: date
    weight_kg: float
    note: str | None = None

    @field_validator("weight_kg")
    @classmethod
    def _peso_plausivel(cls, v):
        if not 30 <= v <= 250:
            raise ValueError("Peso fora da faixa plausivel (30 a 250 kg)")
        return round(v, 1)

    @field_validator("measured_on")
    @classmethod
    def _nao_pode_ser_futuro(cls, v):
        if v > date.today():
            raise ValueError("Nao da para pesar no futuro")
        return v


@router.get("")
def list_weight(db: Session = Depends(get_db)):
    entries = db.scalars(select(WeightEntry).order_by(WeightEntry.measured_on))
    return [
        {"measured_on": e.measured_on.isoformat(), "weight_kg": e.weight_kg, "note": e.note}
        for e in entries
    ]


@router.post("", status_code=201)
def log_weight(payload: WeightInput, db: Session = Depends(get_db)):
    """Upsert por data: relancar o mesmo dia corrige, nao duplica."""
    entry = db.scalar(select(WeightEntry).where(WeightEntry.measured_on == payload.measured_on))
    if entry is None:
        entry = WeightEntry(measured_on=payload.measured_on)
        db.add(entry)
    entry.weight_kg = payload.weight_kg
    entry.note = payload.note
    db.commit()
    return {"measured_on": entry.measured_on.isoformat(), "weight_kg": entry.weight_kg}


@router.delete("/{measured_on}", status_code=204)
def delete_weight(measured_on: date, db: Session = Depends(get_db)):
    entry = db.scalar(select(WeightEntry).where(WeightEntry.measured_on == measured_on))
    if entry is None:
        raise HTTPException(404, "Sem registro de peso nessa data")
    db.delete(entry)
    db.commit()
