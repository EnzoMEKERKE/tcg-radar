<?php
namespace App\Entity;
use Doctrine\ORM\Mapping as ORM;
#[ORM\Entity] class Store { #[ORM\Id, ORM\GeneratedValue, ORM\Column] private ?int $id=null; #[ORM\Column(length:120, unique:true)] public string $name=''; #[ORM\Column(length:255)] public string $baseUrl=''; #[ORM\Column(length:2)] public string $country='FR'; #[ORM\Column(length:3)] public string $currency='EUR'; #[ORM\Column] public bool $enabled=true; #[ORM\Column(nullable:true)] public ?string $strategy=null; public function getId():?int{return $this->id;} }
