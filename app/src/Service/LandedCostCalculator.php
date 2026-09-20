<?php
namespace App\Service;
final class LandedCostCalculator {
 public function calculate(float $priceEur,float $shippingEur,string $origin,bool $vatIncluded=false,float $carrierFee=0,float $customs=0,int $importItems=1): array {
  $eu=['FR','DE','BE','NL','ES','IT','PT','AT','IE','LU','FI','SE','DK','PL','CZ','SK','SI','HR','HU','RO','BG','GR','CY','MT','LT','LV','EE'];
  $outside=$origin!=='UNK' && !in_array(strtoupper($origin),$eu,true);
  $base=$priceEur+$shippingEur;
  $vat=($outside&&!$vatIncluded)?$base*0.20:0;
  // Customs depend on value, tariff category and procedure; never invent a flat charge.
  $flatDuty=0;
  $total=$base+$vat+$flatDuty+$customs+$carrierFee;
  return compact('base','vat','flatDuty','customs','carrierFee','total');
 }
}
