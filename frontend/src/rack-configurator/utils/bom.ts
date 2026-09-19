import type { RackConfig } from "../types";

const BEAM_CAPACITY_KG: Record<RackConfig["rackType"], number> = {
  selective: 2500,
  cantilever: 1800,
  drive_in: 2200,
};

const PALLETS_PER_BAY_LEVEL: Record<RackConfig["rackType"], number> = {
  selective: 2,
  cantilever: 0, // cantilever stores long goods, not palletized slots
  drive_in: 3,
};

export interface BomResult {
  uprightFrames: number;
  beams: number;
  deckPanels: number;
  totalWeightCapacityKg: number;
  totalPalletSlots: number;
  footprintSqM: number;
  footprintSqFt: number;
}

export function computeBom(config: RackConfig): BomResult {
  const { bays, tiers, bayWidthMm, bayDepthMm, rackType } = config;
  const uprightFrames = bays + 1;
  const beamsPerLevel = config.rackType === "cantilever" ? uprightFrames : bays * 2;
  const beams = beamsPerLevel * tiers;
  const deckPanels = rackType === "cantilever" ? 0 : bays * tiers;

  const perLevelCapacity = BEAM_CAPACITY_KG[rackType] * bays;
  const totalWeightCapacityKg = perLevelCapacity * tiers;

  const totalPalletSlots = PALLETS_PER_BAY_LEVEL[rackType] * bays * tiers;

  const totalWidthM = (bays * bayWidthMm) / 1000;
  // Drive-in lanes nest multiple pallet positions deep, so the true floor
  // footprint is bayDepthMm times the nested-position count, matching RackScene's
  // visual lane depth - not just one bay's depth.
  const depthMultiplier = rackType === "drive_in" ? 3 : 1;
  const totalDepthM = (bayDepthMm / 1000) * depthMultiplier;
  const footprintSqM = totalWidthM * totalDepthM;
  const footprintSqFt = footprintSqM * 10.7639;

  return {
    uprightFrames,
    beams,
    deckPanels,
    totalWeightCapacityKg,
    totalPalletSlots,
    footprintSqM,
    footprintSqFt,
  };
}
