import { Beer, Martini, Wine, type LucideIcon } from "lucide-react";
import type { ProductType } from "./api";

// The application fields compared against the label, in display order. Keys
// match the checker's application fields. Change fields here only.
export const APPLICATION_FIELDS = [
  { key: "brand_name", label: "Brand name" },
  { key: "class_type", label: "Class / type" },
  { key: "alcohol_content", label: "Alcohol content" },
  { key: "net_contents", label: "Net contents" },
  { key: "producer_name_address", label: "Bottler / producer name and address" },
  { key: "country_of_origin", label: "Country of origin (imports only)" },
] as const;

export type FieldKey = (typeof APPLICATION_FIELDS)[number]["key"];

export const PRODUCT_TYPES: Record<ProductType, { label: string; Icon: LucideIcon }> = {
  distilled_spirits: { label: "Distilled spirits", Icon: Martini },
  wine: { label: "Wine", Icon: Wine },
  malt_beverage: { label: "Malt beverage", Icon: Beer },
};
