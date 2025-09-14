export type Prospect = {
    id: number;
    company_name: string;
    contact_name?: string | null;
    email?: string | null;
    industry?: string | null;
    revenue_range?: string | null;
    location?: string | null;
    sale_motivation?: string | null;
    signals?: string | null;
    notes?: string | null;
    created_at?: string;
    phone_number?: string | null; // if you add later
  };
  
  export type Slide = { title: string; bullets: string[] };
  
  export type Deck = {
    id: number;
    prospect_id: number;
    title: string;
    slides: Slide[];
    pdf_url: string | null;
  };
  
  export type EmailItem = {
    id: number;
    prospect_id: number;
    sequence_index: number; // 1,2,3
    subject: string;
    body: string;
  };
  
  export type EmailBatch = { items: EmailItem[] };
  