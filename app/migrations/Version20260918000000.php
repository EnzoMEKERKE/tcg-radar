<?php
declare(strict_types=1);
namespace DoctrineMigrations;
use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20260918000000 extends AbstractMigration
{
    public function getDescription(): string { return 'V5 catalogue provenance, case quantities, comparable history and price drops'; }
    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE product ADD canonical BOOLEAN NOT NULL DEFAULT FALSE, ADD catalog_source VARCHAR(500) DEFAULT NULL');
        // Historical V4 quantities are unknown: never reinterpret old cases as a single display.
        $this->addSql('ALTER TABLE offer ADD display_count INT DEFAULT NULL, ADD unit_cost DOUBLE PRECISION DEFAULT NULL, ADD shipping_known BOOLEAN NOT NULL DEFAULT FALSE');
        $this->addSql('ALTER TABLE price_history ADD unit_cost DOUBLE PRECISION DEFAULT NULL, ADD in_stock BOOLEAN NOT NULL DEFAULT FALSE, ADD shipping_known BOOLEAN NOT NULL DEFAULT FALSE');
        $this->addSql('ALTER TABLE price_history ADD product_id INT REFERENCES product(id)');
        $this->addSql('UPDATE price_history SET product_id=offer.product_id FROM offer WHERE offer.id=price_history.offer_id');
        $this->addSql('ALTER TABLE price_history ALTER COLUMN product_id SET NOT NULL');
        $this->addSql('CREATE INDEX IDX_HISTORY_PRODUCT_TIME ON price_history (product_id, recorded_at)');
        $this->addSql('CREATE INDEX IDX_HISTORY_OFFER_TIME ON price_history (offer_id, recorded_at)');
        $this->addSql('CREATE TABLE price_drop (id SERIAL PRIMARY KEY, offer_id INT NOT NULL REFERENCES offer(id), previous_cost DOUBLE PRECISION NOT NULL, new_cost DOUBLE PRECISION NOT NULL, created_at TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL)');
        $this->addSql('CREATE INDEX IDX_DROP_TIME ON price_drop (created_at)');
    }
    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE price_drop');
        $this->addSql('DROP INDEX IDX_HISTORY_OFFER_TIME');
        $this->addSql('DROP INDEX IDX_HISTORY_PRODUCT_TIME');
        $this->addSql('ALTER TABLE price_history DROP product_id');
        $this->addSql('ALTER TABLE price_history DROP unit_cost, DROP in_stock, DROP shipping_known');
        $this->addSql('ALTER TABLE offer DROP display_count, DROP unit_cost, DROP shipping_known');
        $this->addSql('ALTER TABLE product DROP canonical, DROP catalog_source');
    }
}
