-- #669: IsDrivable also covers traffic-only assets. Keep sales restricted
-- to the four hidden variants with full showroom/cockpit model payloads.
-- Never infer player-car compatibility from IsDrivable or expose future
-- rows automatically. See docs/HIDDEN_CARS.md for the per-model audit.
update Data_Car set IsSelectable = 1
  where IsSelectable = 0 and IsDrivable = 1 and Id in (1565, 1566, 1567, 1568);

-- Preserve v1.0's price metadata for cars already bought in modded garages.
update Data_Car set BaseCost = 9000 where Id = 1530 and BaseCost = 0;   -- RAV4 Sport
update Data_Car set BaseCost = 9000 where Id = 1531 and BaseCost = 0;   -- A4 Avant
update Data_Car set BaseCost = 11000 where Id = 1532 and BaseCost = 0;  -- Camry
update Data_Car set BaseCost = 14000 where Id = 1541 and BaseCost = 0;  -- Explorer
update Data_Car set BaseCost = 30000 where Id = 1542 and BaseCost = 0;  -- F-350 Super Duty
update Data_Car set BaseCost = 6000 where Id = 1543 and BaseCost = 0;   -- Focus ZX4
update Data_Car set BaseCost = 100000 where Id = 1529 and BaseCost = 0; -- tour bus
