<?php
namespace App\Entity;
use Doctrine\ORM\Mapping as ORM;
#[ORM\Entity] #[ORM\Index(columns:['game','set_code','language'])] class Product { #[ORM\Id, ORM\GeneratedValue, ORM\Column] private ?int $id=null; #[ORM\Column(length:30)] public string $game=''; #[ORM\Column(length:50)] public string $setCode=''; #[ORM\Column(length:180)] public string $setName=''; #[ORM\Column(length:10)] public string $language='JP'; #[ORM\Column(length:30)] public string $kind='display'; #[ORM\Column(nullable:true)] public ?int $boosters=null; #[ORM\Column] public bool $canonical=false; #[ORM\Column(length:500, nullable:true)] public ?string $catalogSource=null; public function getId():?int{return $this->id;} }
