-- Driver levels at the XP divided by the Rewards option. Wristbands come faster by
-- multiplying the points a finish earns rather than lowering the wristband
-- thresholds, which share their scale with the events' UnlockPointsReq.
update PlayerLevelDef set XP = cast(round(XP * 1.0 / {{rewards}}) as int);
update WristbandScoring set Points = cast(round(Points * {{rewards}}) as int);
