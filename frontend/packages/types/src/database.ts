/**
 * Generated Supabase database types live here.
 *
 * Run `supabase gen types typescript --project-id ... > database.ts`
 * and overwrite this file. Until generated, the placeholder type below lets
 * the workspace compile.
 */

export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export interface Database {
  public: {
    Tables: Record<string, never>;
    Views:  Record<string, never>;
    Functions: Record<string, never>;
    Enums:  Record<string, never>;
  };
}
