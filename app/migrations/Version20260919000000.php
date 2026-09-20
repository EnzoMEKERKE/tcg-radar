<?php
declare(strict_types=1);
namespace DoctrineMigrations;
use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20260919000000 extends AbstractMigration
{
    public function getDescription(): string { return 'Shipping origin evidence and destination-specific import status'; }
    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE offer ADD shipping_origin JSON DEFAULT NULL');
    }
    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE offer DROP shipping_origin');
    }
}
