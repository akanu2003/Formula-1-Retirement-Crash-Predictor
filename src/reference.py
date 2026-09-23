"""Hand-curated season-level reference data: power units and regulation eras.

This file is reviewable data, like src/labels.py. Two things live here:

1. POWER_UNITS: which power unit (engine) supplier each constructor used in
   each season. Suppliers are shared across teams and change over time, so the
   mapping is season-ranged per constructor, keyed by the source's
   constructor_id. Values name the engine's actual manufacturer family, with
   pure sponsor re-badges collapsed to the real maker (see PU_NOTES);
   "Honda RBPT" and "Red Bull Ford" are kept distinct from works "Honda"
   because they are separate programs shared by the two Red Bull teams.

2. REG_RESET_SEASONS: seasons that were the FIRST under a major technical
   regulation reset. The four the project owner named (2014 hybrid V6 power
   units; 2017 wider cars/tyres; 2022 ground-effect aero; 2026 new power
   units + active aero) plus two defensible additions, flagged so they can be
   removed: 2006 (V10 -> V8 engine reset) and 2009 (major aero overhaul +
   KERS introduction).

Compiled from period sources; 2026 supplier lineup verified against 2026
season coverage (motorsport.com / planetf1.com, Sept 2026): Ferrari supplies
Ferrari, Haas and Cadillac; Mercedes supplies Mercedes, McLaren, Williams and
Alpine; Honda supplies Aston Martin; Audi supplies its own works team (the
former Sauber entry, which carries a NEW constructor_id "audi" in the source);
Red Bull Ford supplies Red Bull and RB.
"""

# constructor_id -> list of (first_season, last_season, supplier), inclusive.
POWER_UNITS: dict[str, list[tuple[int, int, str]]] = {
    "alfa":         [(2019, 2023, "Ferrari")],
    "alphatauri":   [(2020, 2021, "Honda"), (2022, 2023, "Honda RBPT")],
    "alpine":       [(2021, 2025, "Renault"), (2026, 2026, "Mercedes")],
    "arrows":       [(2000, 2000, "Supertec"), (2001, 2001, "Asiatech"),
                     (2002, 2002, "Cosworth")],
    "aston_martin": [(2021, 2025, "Mercedes"), (2026, 2026, "Honda")],
    "audi":         [(2026, 2026, "Audi")],
    "bar":          [(2000, 2005, "Honda")],
    "benetton":     [(2000, 2000, "Supertec"), (2001, 2001, "Renault")],
    "bmw_sauber":   [(2006, 2009, "BMW")],
    "brawn":        [(2009, 2009, "Mercedes")],
    "cadillac":     [(2026, 2026, "Ferrari")],
    "caterham":     [(2012, 2014, "Renault")],
    "ferrari":      [(2000, 2026, "Ferrari")],
    "force_india":  [(2008, 2008, "Ferrari"), (2009, 2018, "Mercedes")],
    "haas":         [(2016, 2026, "Ferrari")],
    "honda":        [(2006, 2008, "Honda")],
    "hrt":          [(2010, 2012, "Cosworth")],
    "jaguar":       [(2000, 2004, "Cosworth")],
    "jordan":       [(2000, 2000, "Mugen-Honda"), (2001, 2002, "Honda"),
                     (2003, 2004, "Ford"), (2005, 2005, "Toyota")],
    "lotus_f1":     [(2012, 2014, "Renault"), (2015, 2015, "Mercedes")],
    "lotus_racing": [(2010, 2010, "Cosworth"), (2011, 2011, "Renault")],
    "manor":        [(2015, 2015, "Ferrari"), (2016, 2016, "Mercedes")],
    "marussia":     [(2012, 2013, "Cosworth"), (2014, 2014, "Ferrari")],
    "mclaren":      [(2000, 2014, "Mercedes"), (2015, 2017, "Honda"),
                     (2018, 2020, "Renault"), (2021, 2026, "Mercedes")],
    "mercedes":     [(2010, 2026, "Mercedes")],
    "mf1":          [(2006, 2006, "Toyota")],
    "minardi":      [(2000, 2001, "Ford"), (2002, 2002, "Asiatech"),
                     (2003, 2005, "Cosworth")],
    "prost":        [(2000, 2000, "Peugeot"), (2001, 2001, "Ferrari")],
    "racing_point": [(2019, 2020, "Mercedes")],
    "rb":           [(2024, 2025, "Honda RBPT"), (2026, 2026, "Red Bull Ford")],
    "red_bull":     [(2005, 2005, "Cosworth"), (2006, 2006, "Ferrari"),
                     (2007, 2018, "Renault"), (2019, 2021, "Honda"),
                     (2022, 2025, "Honda RBPT"), (2026, 2026, "Red Bull Ford")],
    "renault":      [(2002, 2020, "Renault")],
    "sauber":       [(2000, 2005, "Ferrari"), (2010, 2018, "Ferrari"),
                     (2024, 2025, "Ferrari")],
    "spyker":       [(2007, 2007, "Ferrari")],
    "spyker_mf1":   [(2006, 2006, "Toyota")],
    "super_aguri":  [(2006, 2008, "Honda")],
    "toro_rosso":   [(2006, 2006, "Cosworth"), (2007, 2013, "Ferrari"),
                     (2014, 2015, "Renault"), (2016, 2016, "Ferrari"),
                     (2017, 2017, "Renault"), (2018, 2019, "Honda")],
    "toyota":       [(2002, 2009, "Toyota")],
    "virgin":       [(2010, 2011, "Cosworth")],
    "williams":     [(2000, 2005, "BMW"), (2006, 2006, "Cosworth"),
                     (2007, 2009, "Toyota"), (2010, 2011, "Cosworth"),
                     (2012, 2013, "Renault"), (2014, 2026, "Mercedes")],
}

# Badge collapses and lower-confidence entries, recorded like UNSURE in labels.
PU_NOTES = {
    "arrows 2000": "badged 'Supertec' - a rebadged Renault-lineage V10",
    "benetton 2000": "badged 'Playlife' - actually a Supertec unit",
    "prost 2001": "badged 'Acer' - actually a customer Ferrari",
    "sauber 2000-2005": "badged 'Petronas' - actually year-old customer Ferraris",
    "minardi 2001": "badged 'European' - actually a Ford Zetec-R",
    "arrows/minardi Asiatech": "Asiatech = rebadged ex-Peugeot program",
    "red_bull 2016-2018": "badged 'TAG Heuer' - actually Renault",
    "toro_rosso 2016": "year-old 2015-spec Ferrari",
    "Honda RBPT 2022-2025": "Honda-built units run by Red Bull Powertrains",
    "cadillac 2026": "customer Ferrari units (GM's own engine comes later)",
}

# Seasons that opened a major technical regulation era.
REG_RESET_SEASONS = {2006, 2009, 2014, 2017, 2022, 2026}
# 2014, 2017, 2022, 2026 named by the project owner; 2006 and 2009 added -
# see module docstring. Remove a year here to change the definition.


def power_unit_for(constructor_id: str, season: int) -> str | None:
    """Supplier for one constructor-season, or None if not mapped."""
    for first, last, supplier in POWER_UNITS.get(constructor_id, []):
        if first <= season <= last:
            return supplier
    return None


def add_reference_columns(df):
    """Add power_unit and reg_reset columns to a results-like frame."""
    out = df.copy()
    out["power_unit"] = [
        power_unit_for(c, s) for c, s in zip(out["constructor_id"], out["season"])
    ]
    out["reg_reset"] = out["season"].isin(REG_RESET_SEASONS)
    return out
