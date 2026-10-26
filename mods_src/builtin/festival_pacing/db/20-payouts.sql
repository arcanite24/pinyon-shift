-- Credits for a finish, an event's cash prize and a car make's loyalty bonus,
-- multiplied by the Rewards option.
update EventScoring set Credits = cast(round(Credits * {{rewards}}) as int);
update Events set CashPrize = cast(round(CashPrize * {{rewards}}) as int);
update AffinityLevelDef set BonusCredits = cast(round(BonusCredits * {{rewards}}) as int);
