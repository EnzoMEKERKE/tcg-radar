<?php
namespace App\Entity;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
class PriceDrop
{
    #[ORM\Id, ORM\GeneratedValue, ORM\Column] public ?int $id = null;
    #[ORM\ManyToOne] #[ORM\JoinColumn(nullable:false)] public Offer $offer;
    #[ORM\Column] public float $previousCost;
    #[ORM\Column] public float $newCost;
    #[ORM\Column] public \DateTimeImmutable $createdAt;
    public function __construct() { $this->createdAt = new \DateTimeImmutable(); }
}
