<?php
namespace App\Entity;
use Doctrine\ORM\Mapping as ORM;
#[ORM\Entity] class PriceHistory { #[ORM\Id, ORM\GeneratedValue, ORM\Column] private ?int $id=null; #[ORM\ManyToOne] #[ORM\JoinColumn(nullable:false)] public Offer $offer; #[ORM\ManyToOne] #[ORM\JoinColumn(nullable:false)] public Product $product; #[ORM\Column] public float $price=0; #[ORM\Column] public float $landedCost=0; #[ORM\Column] public \DateTimeImmutable $recordedAt; #[ORM\Column(nullable:true)] public ?float $unitCost=null; #[ORM\Column] public bool $inStock=true; #[ORM\Column] public bool $shippingKnown=false; public function __construct(){ $this->recordedAt=new \DateTimeImmutable(); } }
