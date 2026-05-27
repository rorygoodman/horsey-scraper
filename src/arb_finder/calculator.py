"""Each-way edge + the join that prices every fully-priced runner."""

from __future__ import annotations

from common.markettype import MarketType, top_n_from_places
from betfair_scraper.models import ScrapeOutput
from paddypower_scraper.models import PaddyOutput
from .models import BetfairLayLeg, Horse, PaddyPriceLeg, Runner


def each_way_arb_margin(p: float, f: float, bw: float, bp: float) -> float:
    """Each-way edge per £1 PaddyPower stake (signed):

      L_w  = p / (2·bw)
      L_p  = (1 + (p−1)·f) / (2·bp)
      edge = L_w + L_p − 1
    """
    lw = p / (2.0 * bw)
    lp = (1.0 + (p - 1.0) * f) / (2.0 * bp)
    return lw + lp - 1.0


def find_horses(betfair: ScrapeOutput, paddy: PaddyOutput) -> list[Horse]:
    """Every fully-priced runner with its each-way edge, sorted by edge
    descending. A runner is included when its PaddyPower win price, the
    Betfair WIN lay, and the Betfair place (TOP_N matching PP's places) lay
    are all present and > 0. The edge may be negative."""
    betfair_by_id = {r.race_id: r for r in betfair.races}
    out: list[Horse] = []

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
        place_market = top_n_from_places(ew.places)
        if place_market is None or place_market not in br.market_scraped_at:
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
            place_lay = brun.lay.get(place_market)
            if (win_lay is None or place_lay is None
                    or win_lay <= 0.0 or place_lay <= 0.0):
                continue

            edge = each_way_arb_margin(p=pp_price, f=ew.fraction, bw=win_lay, bp=place_lay)
            out.append(Horse(
                venue=pr.venue,
                country=pr.country,
                off_time=pr.off_time,
                market_name=pr.market_name,
                betfair_win_market_id=win_market_id,
                runner=Runner(name=prun.name, selection_id=sel),
                paddypower=PaddyPriceLeg(
                    win_price=pp_price, win_price_raw=pp_raw, each_way_terms=ew),
                betfair=BetfairLayLeg(
                    win_lay=win_lay, place_lay=place_lay, place_market=place_market),
                edge=edge,
            ))

    out.sort(key=lambda h: h.edge, reverse=True)
    return out
