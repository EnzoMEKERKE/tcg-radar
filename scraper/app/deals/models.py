from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class Listing(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    source: Literal['ebay', 'cardmarket']
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(max_length=2000)
    price: float = Field(gt=0, le=1000000)
    currency: Literal['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'CAD'] = 'EUR'
    shipping: float | None = Field(default=None, ge=0, le=10000)
    language: Literal['FR', 'EN', 'JP', 'DE', 'IT', 'ES', 'KR', 'CN', 'UNKNOWN'] = 'UNKNOWN'
    condition: Literal['MT', 'NM', 'EX', 'GD', 'LP', 'PL', 'PO', 'UNKNOWN'] = 'UNKNOWN'
    card_number: str = Field(default='', max_length=40)
    set_code: str = Field(default='', max_length=100)
    variant: str = Field(default='', max_length=80)
    sold: bool = False
    sold_at: datetime | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    available: bool = True
    seller: str = Field(default='', max_length=120)
    listing_id: str = Field(default='', max_length=120)
    price_exact: bool = True
    provenance: Literal['scraped', 'imported'] = 'scraped'

    @field_validator('url')
    @classmethod
    def public_listing_url(cls, value):
        p = urlsplit(value)
        hosts = ('ebay.fr', 'ebay.com', 'ebay.co.uk', 'ebay.de', 'ebay.it', 'ebay.es', 'cardmarket.com')
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443) or not any(p.hostname in (host, 'www.'+host) for host in hosts):
            raise ValueError('Lien eBay ou Cardmarket HTTPS requis')
        return value

    @field_validator('observed_at', 'sold_at')
    @classmethod
    def utc(cls, value):
        if value is None:
            return value
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc):
            raise ValueError('Date future non autorisée')
        return value

    @model_validator(mode='after')
    def source_matches(self):
        host = urlsplit(self.url).hostname
        if (self.source == 'cardmarket') != (host in ('cardmarket.com', 'www.cardmarket.com')):
            raise ValueError('Le lien ne correspond pas à la source')
        return self


class BrowserRequest(BaseModel):
    query: str = Field(default='', max_length=120)
    manual: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    query: str = Field(default='', max_length=120)
    language: Literal['ALL', 'FR', 'EN', 'JP', 'DE', 'IT', 'ES', 'KR', 'CN'] = 'FR'
    condition_min: Literal['MT', 'NM', 'EX', 'GD', 'LP', 'PL', 'PO'] = 'NM'
    direction: Literal['all', 'cm_to_ebay', 'ebay_to_cm'] = 'all'
    min_profit: float = Field(default=5, ge=0, le=100000)
    min_roi: float = Field(default=10, ge=0, le=1000)
    min_sales: int = Field(default=3, ge=1, le=100)
    sales_days: int = Field(default=90, ge=1, le=365)
    # Editable planning assumptions, NOT a claim about platform fee schedules.
    ebay_fee_pct: float = Field(default=13, ge=0, le=50)
    cm_fee_pct: float = Field(default=5, ge=0, le=50)
    fixed_fee: float = Field(default=0.35, ge=0, le=100)
    buy_shipping: float = Field(default=3, ge=0, le=1000)
    sell_shipping: float = Field(default=3, ge=0, le=1000)
    packaging: float = Field(default=0.5, ge=0, le=100)
    other_costs: float = Field(default=0, ge=0, le=10000)
    safety_pct: float = Field(default=5, ge=0, le=90)
    pages: int = Field(default=3, ge=1, le=10)
    max_cards: int = Field(default=15, ge=1, le=50)
    force: bool = False


class ImportRequest(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    csv: str = Field(min_length=1, max_length=2000000)
