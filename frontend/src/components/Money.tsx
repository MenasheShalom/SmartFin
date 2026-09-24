import { formatMoney, type Decimals, type Sign } from "../lib/format";

interface Props {
  value: string | number | null | undefined;
  decimals?: Decimals;
  sign?: Sign;
  className?: string;
}

/** An amount kept left-to-right inside Hebrew text */
export function Money({ value, decimals, sign, className }: Props) {
  return <bdi className={className ? `money ${className}` : "money"}>{formatMoney(value, { decimals, sign })}</bdi>;
}
