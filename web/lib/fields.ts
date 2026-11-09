interface FieldDef {
  key: string;
  label: string;
  placeholder: string;
  hint?: string;
  wide?: boolean;
}

// The application fields the checker compares against the label. Keys match
// the checker's form fields and CSV columns. Change fields here only.
const DEFS = [
  { key: "brand_name", label: "Brand name", placeholder: "OLD TOM DISTILLERY" },
  { key: "class_type", label: "Class / type", placeholder: "Kentucky Straight Bourbon Whiskey" },
  { key: "alcohol_content", label: "Alcohol content", placeholder: "45% Alc./Vol. (90 Proof)" },
  { key: "net_contents", label: "Net contents", placeholder: "750 mL" },
  {
    key: "producer_name_address",
    label: "Bottler / producer name and address",
    placeholder: "Bottled by Old Tom Distillery, Bardstown, KY",
    wide: true,
  },
  { key: "country_of_origin", label: "Country of origin", hint: "imports only", placeholder: "Scotland" },
] as const satisfies readonly FieldDef[];

export type FieldKey = (typeof DEFS)[number]["key"];
export type Application = Record<FieldKey, string>;

export const APPLICATION_FIELDS: readonly (FieldDef & { key: FieldKey })[] = DEFS;

// The batch table names each label by this field.
export const IDENTIFYING_FIELD = APPLICATION_FIELDS[0];

export function emptyApplication(): Application {
  return Object.fromEntries(APPLICATION_FIELDS.map((f) => [f.key, ""])) as Application;
}

export function isApplicationField(key: string): key is FieldKey {
  return APPLICATION_FIELDS.some((f) => f.key === key);
}
