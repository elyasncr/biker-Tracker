"""Descobre qual bike foi usada em cada treino.

A deteccao automatica funciona SO SE os sensores moram numa bike so. Quando o
ciclista compra sensores avulsos e passa a mesma dupla de uma bike para outra -
que e o caso comum - a assinatura para de identificar a bike e passa a identificar
o conjunto de sensores. Ai ela vira uma armadilha: atribuiria todos os pedais a
mesma bike com confianca total e errada.

Por isso existe a deteccao de conflito abaixo. No momento em que a mesma assinatura
e reivindicada por duas bikes diferentes, o sistema conclui que os sensores viajam,
marca aquela assinatura como ambigua e PARA de adivinhar. Dali em diante os treinos
com aqueles sensores ficam esperando atribuicao manual - que e rapida, porque da
para atribuir um periodo inteiro de uma vez.

Errar em silencio seria pior do que perguntar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, Bike


def signature_is_ambiguous(db: Session, signature: str | None) -> bool:
    """A mesma assinatura pertence a mais de uma bike? Entao os sensores viajam."""
    if not signature:
        return False
    owners = 0
    for bike in db.scalars(select(Bike)):
        if signature in (bike.signatures or []):
            owners += 1
    return owners > 1


def match_bike(db: Session, signature: str | None) -> Bike | None:
    """Acha a bike dona desta assinatura, ou cai na bike padrao.

    Devolve None quando a assinatura e ambigua: melhor deixar o treino sem dono do
    que carimbar a bike errada em cima dele.
    """
    if signature and signature_is_ambiguous(db, signature):
        return None

    if signature:
        for bike in db.scalars(select(Bike)):
            if signature in (bike.signatures or []):
                return bike
        # Casamento parcial: trocar a cinta ou perder um sensor nao muda a bike.
        incoming = set(signature.split("|"))
        best: tuple[float, Bike] | None = None
        for bike in db.scalars(select(Bike)):
            for known in bike.signatures or []:
                overlap = incoming & set(known.split("|"))
                if not overlap:
                    continue
                ratio = len(overlap) / max(len(incoming), len(set(known.split("|"))))
                if ratio >= 0.5 and (best is None or ratio > best[0]):
                    best = (ratio, bike)
        if best:
            return best[1]

    return db.scalar(select(Bike).where(Bike.is_default.is_(True)))


def learn_signature(db: Session, bike: Bike, signature: str | None) -> None:
    """Ensina uma assinatura nova a uma bike ja conhecida."""
    if not signature:
        return
    known = list(bike.signatures or [])
    if signature not in known:
        known.append(signature)
        bike.signatures = known


def assign_and_learn(db: Session, activity: Activity, bike: Bike) -> tuple[int, bool]:
    """Atribui a bike a este treino e, se for seguro, adota os treinos orfaos iguais.

    Se a assinatura ja pertence a outra bike, os sensores viajam entre elas. Nesse
    caso a adocao em massa e desligada e devolvemos conflict=True para a interface
    avisar que dali em diante a atribuicao vai ser manual.
    """
    signature = activity.sensor_signature
    conflict = bool(
        signature
        and any(signature in (other.signatures or []) and other.id != bike.id for other in db.scalars(select(Bike)))
    )

    activity.bike_id = bike.id
    learn_signature(db, bike, signature)

    adopted = 0
    if signature and not conflict:
        orphans = db.scalars(
            select(Activity).where(
                Activity.bike_id.is_(None),
                Activity.sensor_signature == activity.sensor_signature,
            )
        )
        for orphan in orphans:
            orphan.bike_id = bike.id
            adopted += 1

    db.commit()
    return adopted, conflict


def assign_range(db: Session, bike: Bike, start, end) -> int:
    """Atribui um periodo inteiro de uma vez.

    Quando os sensores viajam entre bikes, a memoria do ciclista e o unico dado
    confiavel - e ela funciona por periodo ("de maio ate julho andei na gravel"),
    nao pedal por pedal.
    """
    count = 0
    for ride in db.scalars(select(Activity).where(Activity.started_at >= start, Activity.started_at <= end)):
        ride.bike_id = bike.id
        count += 1
    db.commit()
    return count


def bike_stats(db: Session, bike: Bike) -> dict:
    """Odometro por bike - util para saber quando trocar corrente e pneu."""
    rides = list(db.scalars(select(Activity).where(Activity.bike_id == bike.id)))
    distance = sum(r.distance_km for r in rides)
    return {
        "activities": len(rides),
        "distance_km": round(distance, 1),
        "moving_time_h": round(sum(r.moving_time_s for r in rides) / 3600, 1),
        "elevation_gain_m": round(sum(r.elevation_gain_m for r in rides)),
        "last_ride": max((r.started_at for r in rides), default=None),
        # Referencias comuns de manutencao, contadas desde o primeiro treino registrado
        "chain_due_in_km": round(max(0, 3000 - distance % 3000), 1) if distance else None,
    }
