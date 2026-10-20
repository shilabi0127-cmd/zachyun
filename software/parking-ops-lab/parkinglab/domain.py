"""Validated public input formats and CSV handling."""
import csv
import io
import random
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)
    id: str = Field(pattern=r"^[A-Za-z0-9_\u4e00-\u9fff-]{1,40}$")
    start: float = Field(ge=0, le=1440)
    end: float = Field(gt=0, le=1440)
    fee: float = Field(default=10, ge=0, le=10000)
    priority: float = Field(default=1, ge=1, le=10)
    arrival_mean: float = Field(default=-2, ge=-60, le=60)
    arrival_std: float = Field(default=4, ge=0, le=60)
    departure_mean: float = Field(default=4, ge=-60, le=60)
    departure_std: float = Field(default=5, ge=0, le=60)

    @field_validator("start", "end", mode="before")
    @classmethod
    def clock_or_minutes(cls, value):
        if isinstance(value, str) and ":" in value:
            parts = value.split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                raise ValueError("时间应为分钟数或HH:MM")
            h, m = map(int, parts)
            if not 0 <= h <= 24 or not 0 <= m < 60 or (h == 24 and m != 0):
                raise ValueError("时间超出00:00至24:00")
            return h * 60 + m
        return value

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end - self.start < 5:
            raise ValueError("预约时长至少5分钟，结束时间必须晚于开始时间")
        return self


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, validate_default=True)
    slots: int = Field(default=4, ge=1, le=20)
    risk_budget: float = Field(default=.1, ge=.01, le=.5)
    trials: int = Field(default=500, ge=50, le=3000)
    seed: int = Field(default=20261020, ge=0, le=2**32 - 1)
    objective: Literal["weighted_admission", "revenue"] = "weighted_admission"
    time_limit: float = Field(default=8, ge=.1, le=20)


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reservations: list[Reservation] = Field(min_length=1, max_length=300)
    config: ExperimentConfig = Field(default_factory=ExperimentConfig)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [r.id for r in self.reservations]
        if len(ids) != len(set(ids)):
            raise ValueError("预约ID不能重复")
        return self


CSV_FIELDS = list(Reservation.model_fields)


def parse_csv(text: str) -> list[Reservation]:
    if len(text.encode("utf-8")) > 1_000_000:
        raise ValueError("CSV最大为1MB")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"id", "start", "end"} <= set(reader.fieldnames):
        raise ValueError("CSV必须包含id、start、end列")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("CSV列名不能重复")
    unknown = set(reader.fieldnames) - set(CSV_FIELDS)
    if unknown:
        raise ValueError("未知列 " + ", ".join(sorted(unknown)))
    result = []
    for line, row in enumerate(reader, 2):
        if None in row:
            raise ValueError(f"第{line}行的列数与表头不一致")
        values = {k: v.strip() for k, v in row.items() if v is not None and v.strip()}
        try:
            result.append(Reservation.model_validate(values))
        except ValueError as error:
            raise ValueError(f"第{line}行数据无效 {error}") from error
        if len(result) > 300:
            raise ValueError("最多支持300条预约")
    if not result:
        raise ValueError("CSV中没有预约数据")
    ids = [r.id for r in result]
    if len(ids) != len(set(ids)):
        raise ValueError("预约ID不能重复")
    return result


def to_csv(reservations: list[Reservation]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(r.model_dump() for r in reservations)
    return stream.getvalue()


def sample_reservations(count=48, seed=20261020):
    if not 1 <= count <= 300:
        raise ValueError("样本量必须在1至300之间")
    rng = random.Random(seed)
    reservations = []
    for i in range(count):
        start = rng.randrange(480, 901, 5)
        duration = rng.choice([30, 45, 60, 75, 90])
        priority = 4 if rng.random() < .3 else 1
        reservations.append(Reservation(id=f"R{i+1:03}", start=start, end=start+duration,
                                        fee=round(duration / 60 * rng.uniform(6, 12), 2),
                                        priority=priority))
    return reservations
