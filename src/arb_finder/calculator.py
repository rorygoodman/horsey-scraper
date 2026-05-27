"""Each-way arbitrage margin + the join that finds opportunities.
Port of ArbCalculator.kt."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places
from betfair_scraper.models import ScrapeOutput
from paddypower_scraper.models import PaddyOutput
from .models import Arb, ArbRunner, BetfairLayLeg, PaddyPriceLeg


def each_way_arb_margin(p: float, f: float, bw: float, bp: float) -> float:
    """Guaranteed profit per £1 PaddyPower each-way stake.

      L_w    = p / (2·bw)
      L_p    = (1 + (p−1)·f) / (2·bp)
      margin = L_w + L_p − 1"""
    lw = p / (2.0 * bw)
    lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0


def find_arbs(betfair: ScrapeOutput, paddy: PaddyOutput) -> list[Arb]:
    """Positive-margin each-way arbs, sorted by margin descending."""
    betfair_by_id = {r.race_id: r for r in betfair.races}
    out: list[Arb] = []

    for pr in paddy.races:
        win_market_id = pr.betfair_win_market_id
        if win_market_id is None:
            continue
        br = betfair_by_id.get(win_market_id)
        if br is None:
            continue
        ew = pr.each_way_terms
        if ew is None:
            continue
        top_n_type = top_n_from_places(ew.places)
        if top_n_type is None or top_n_type not in br.market_scraped_at:
            continue

        bf_by_sel = {r.selection_id: r for r in br.runners if r.selection_id is not None}

        for prun in pr.runners:
            sel = prun.selection_id
            if sel is None:
                continue
            brun = bf_by_sel.get(sel)
            if brun is None:
                continue
            pp_price = prun.win_price
            pp_raw = prun.win_price_raw
            if pp_price is None or pp_raw is None:
                continue
            win_lay = brun.lay.get(MarketType.WIN)
            top_n_lay = brun.lay.get(top_n_type)
            # Skip missing or non-positive lays. Betfair's price floor is 1.01,
            # so <= 0 only arises from corrupt input; guarding avoids a
            # ZeroDivisionError in the margin formula (the JVM oracle would
            # instead yield an Infinity-margin arb here).
            if (win_lay is None or top_n_lay is None
                    or win_lay <= 0.0 or top_n_lay <= 0.0):
                continue

            margin = each_way_arb_margin(p=pp_price, f=ew.fraction, bw=win_lay, bp=top_n_lay)
            if margin <= 0.0:
                continue

            out.append(Arb(
                venue=pr.venue,
                country=pr.country,
                off_time=pr.off_time,
                market_name=pr.market_name,
                betfair_win_market_id=win_market_id,
                runner=ArbRunner(name=prun.name, selection_id=sel),
                paddypower=PaddyPriceLeg(
                    win_price=pp_price, win_price_raw=pp_raw, each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, top_n_lay=top_n_lay, top_n_type=top_n_type),
                margin=margin,
            ))

    out.sort(key=lambda a: a.margin, reverse=True)
    return out
