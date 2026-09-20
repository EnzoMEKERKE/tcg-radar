from dataclasses import dataclass
@dataclass
class CostInput: price_eur:float; shipping_eur:float=0; origin:str="FR"; vat_included:bool=True; carrier_fee:float=0; import_flat_fee:float=0

def landed_cost(x:CostInput)->float:
    base=x.price_eur+x.shipping_eur
    vat=0 if x.origin in {"FR","EU"} or x.vat_included else base*.20
    return round(base+vat+x.carrier_fee+x.import_flat_fee,2)
