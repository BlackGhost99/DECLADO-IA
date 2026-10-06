// Type definitions for DECLADO-IA application

export interface BackendHealth {
  status: string;
  version: string;
  database: string;
  message?: string;
}

export interface OCRResult {
  source: string;
  num_pages: number;
  pages: OCRPage[];
  normalized: NormalizedFields;
  cer?: number;
  warnings: string[];
}

export interface OCRPage {
  page_index: number;
  width: number;
  height: number;
  text: string;
  words: OCRWord[];
  tables: unknown[];
}

export interface OCRWord {
  text: string;
  bbox: [number, number, number, number];
  confidence: number;
}

export interface NormalizedFields {
  dates: string[];
  amounts: number[];
  currencies: string[];
  vendor?: string;
}

export interface HSClassification {
  code: string;
  description: string;
  confidence: number;
}

export interface CustomsCalculation {
  calculation_id: string;
  input: CustomsInput;
  incoterms_conversion: IncotermsConversion;
  taxable_base: string;
  tax_breakdown: TaxBreakdown;
  required_documents: string[];
  warnings: string[];
  audit_log: AuditLog;
}

export interface CustomsInput {
  invoice_number: string;
  hs_code: string;
  description: string;
  quantity: number | string;
  unit_price: number | string;
  currency: string;
  incoterm: string;
  origin_country: string;
  destination_country: string;
  freight_cost?: number | string;
  insurance_cost?: number | string;
  exchange_rate?: number | string;
  exemption_code?: string;
}

export interface IncotermsConversion {
  original_incoterm: string;
  original_value: string;
  freight_cost: string;
  insurance_cost: string;
  cif_value: string;
  formula: string;
}

export interface TaxBreakdown {
  customs_duty_rate: string;
  customs_duty_amount: string;
  vat_rate: string;
  vat_base: string;
  vat_amount: string;
  other_taxes: Record<string, string>;
  total_taxes: string;
  total_amount: string;
}

export interface AuditLog {
  calculation_id: string;
  entries: AuditEntry[];
  created_at: string;
}

export interface AuditEntry {
  step: string;
  formula: string;
  inputs: Record<string, string>;
  output: string | number;
  notes?: string;
}

export interface InvoiceDocument {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  uploadedAt: Date;
  ocrResult?: OCRResult;
  hsClassifications?: HSClassification[];
  customsCalculation?: CustomsCalculation;
  error?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  createdAt: Date;
  documents: InvoiceDocument[];
}

export interface ExportRequest {
  format: 'pdf' | 'xml_esad' | 'csv' | 'json';
  calculation: CustomsInput;
  meta?: ExportMeta;
}

export interface ExportMeta {
  declaration_number?: string;
  declarant_name?: string;
  exporter_name?: string;
  importer_name?: string;
  customs_office?: string;
  country?: string;
  declaration_date?: string;
}
