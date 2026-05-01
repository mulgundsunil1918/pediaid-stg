#!/usr/bin/env python3
"""
add_keywords.py — patch stg_index.json with curated keywords per chapter.

Each chapter gets 2-5 keywords covering:
  - common synonym(s)
  - abbreviation OR full form (whichever isn't already the title)
  - one or two clinical / lay terms users might search

Usage
─────
    python scripts/add_keywords.py

Reads stg_index.json (at the repo root), updates the `keywords` field
on every chapter where we have a curated list, and writes the file back.
Chapters not in the curated map keep their existing keywords (or stay
empty).

After running:
    git add stg_index.json
    git commit -m "Add curated keywords to STG index"
    git push
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

INDEX_PATH = Path(__file__).resolve().parent.parent / "stg_index.json"


# Title → keywords. Keys are matched case-insensitively against the chapter
# title, normalised (alnum+spaces). Multiple title variants are listed
# where the PDF wording differed from the original index.
KEYWORDS: dict[str, list[str]] = {
    "Neonatal Hypoglycemia": ["hypoglycemia", "low blood sugar", "BSL", "dextrose"],
    "Atopic Dermatitis": ["eczema", "AD", "atopic eczema", "skin rash"],
    "Anaphylaxis": ["allergic shock", "adrenaline", "epinephrine"],
    "Difficulties in Breathing": ["respiratory distress", "dyspnoea", "breathlessness"],
    "Neonatal Sepsis": ["sepsis", "EONS", "LONS", "blood culture"],
    "UTI": ["urinary tract infection", "urinary infection", "pyelonephritis", "cystitis"],
    "Food Allergy": ["IgE allergy", "food intolerance", "anaphylaxis food"],
    "Enteric Fever": ["typhoid", "salmonella", "paratyphoid"],
    "Menstrual Irregularities": ["menorrhagia", "dysmenorrhea", "amenorrhea", "AUB"],
    "Croup in children": ["laryngotracheobronchitis", "barking cough", "stridor", "LTB"],
    "Community Acquired Pneumonia": ["CAP", "pneumonia", "lung infection"],
    "Hypothyroidism": ["congenital hypothyroidism", "CH", "low thyroid"],
    "Rickets": ["vitamin D deficiency", "bow legs", "osteomalacia"],
    "Allergic Rhinitis": ["AR", "hay fever", "nasal allergy"],
    "Viral Hepatitis": ["hepatitis A", "hepatitis B", "HAV", "HBV"],
    "Enuresis": ["bedwetting", "nocturnal enuresis"],
    "Sinusitis": ["rhinosinusitis", "sinus infection"],
    "Acute Pharyngitis / Acute Tonsillopharyngitis":
        ["sore throat", "tonsillitis", "GAS", "group A strep"],
    "Post Covid Lung": ["long covid", "post-covid", "covid sequelae"],
    "Acute Watery Diarrhea": ["AWD", "gastroenteritis", "dehydration", "ORS"],
    "Leptospirosis": ["lepto", "Weil disease"],
    "Diabetes Mellitus": ["DM", "T1DM", "T2DM", "insulin"],
    "Urticaria": ["hives", "wheal"],
    "Acute Otitis Media": ["AOM", "ear infection", "otitis"],
    "Acute Rheumatic Fever": ["ARF", "rheumatic heart disease", "RHD", "Jones criteria"],
    "Childhood Obesity": ["obesity", "BMI", "overweight"],
    "Bronchiolitis": ["RSV", "viral bronchiolitis", "infant wheeze"],
    "Febrile Neutropenia": ["FN", "neutropenic fever"],
    "Empyema": ["pleural empyema", "parapneumonic effusion"],
    "Persistent Diarrhea": ["chronic diarrhea", "malabsorption"],
    "SLE": ["systemic lupus erythematosus", "lupus", "autoimmune"],
    "HSP": ["Henoch Schonlein purpura", "IgA vasculitis"],
    "Growing Pains": ["leg pain children", "benign limb pain"],
    "Heart Failure": ["CCF", "congestive heart failure", "cardiac failure"],
    "Bronchial Asthma": ["asthma", "wheeze", "bronchodilator"],
    "Supraventricular Tachycardia": ["SVT", "fast heart rate", "palpitation"],
    "Herpes Simplex": ["HSV", "cold sore"],
    "Indications and Timing of Surgeries in Congenital Heart Diseases":
        ["CHD surgery", "congenital heart", "cardiac surgery"],
    "Rickettsial Disease": ["spotted fever", "scrub typhus", "rickettsia"],
    "Status Epilepticus in Children": ["SE", "prolonged seizure", "refractory seizure"],
    "Protracted Bacterial Bronchitis": ["PBB", "chronic cough"],
    "Kawasaki Disease": ["KD", "mucocutaneous lymph node syndrome"],
    "G6PD Deficiency":
        ["G6PD", "glucose 6 phosphate dehydrogenase", "favism", "hemolytic anemia"],
    "Megaloblastic Anemia": ["vitamin B12 deficiency", "folate deficiency", "macrocytic anemia"],
    "Under 5 Wheeze": ["preschool wheeze", "viral wheeze", "recurrent wheeze"],
    "Sickle Cell Disease - Management":
        ["SCD", "sickle cell", "HbSS", "vaso-occlusive crisis"],
    "Acute Gastrointestinal Bleed":
        ["UGI bleed", "hematemesis", "melena", "GI bleeding"],
    "Febrile Seizures":
        ["febrile convulsion", "simple febrile seizure", "complex febrile seizure"],
    "Atypical Bacterial Pneumonia": ["mycoplasma", "chlamydia", "walking pneumonia"],
    "Varicella": ["chickenpox", "VZV"],
    "Juvenile Idiopathic Arthritis":
        ["JIA", "JRA", "juvenile arthritis", "juvenile rheumatoid arthritis"],
    "GBS": ["Guillain Barre syndrome", "ascending paralysis", "AIDP"],
    "Pneumothorax in children":
        ["pneumothorax", "collapsed lung", "tension pneumothorax"],
    "Infectious Mononucleosis": ["EBV", "mono", "glandular fever"],
    "CPR-BLS in Office Practice":
        ["CPR", "cardiopulmonary resuscitation", "basic life support", "BLS"],
    "Acute Bacterial Meningitis":
        ["ABM", "bacterial meningitis", "CSF", "lumbar puncture"],
    "Hypertension": ["HTN", "high blood pressure", "BP"],
    "Acute Epiglottitis": ["epiglottitis", "supraglottitis"],
    "Iron Deficiency Anemia": ["IDA", "iron deficiency", "anemia"],
    "Hand, Foot and Mouth Disease": ["HFMD", "coxsackie", "hand foot mouth"],
    "Hemophilia": ["factor VIII", "factor IX", "bleeding disorder"],
    "Preterm with Respiratory Distress":
        ["preterm RDS", "respiratory distress syndrome", "surfactant"],
    "Multisystem Inflammatory Syndrome":
        ["MIS-C", "post-covid inflammatory", "MISC"],
    "Nephrotic Syndrome": ["NS", "proteinuria", "minimal change disease", "edema"],
    "Acute Covid-19 Infection in Children": ["COVID", "SARS-CoV-2", "coronavirus"],
    "Developmental Dysplasia of the Hip":
        ["DDH", "hip dysplasia", "congenital hip dislocation"],
    "Neonatal Hypothermia": ["cold stress", "hypothermic neonate", "low temperature"],
    "Ophthalmia Neonatorum":
        ["neonatal conjunctivitis", "eye discharge newborn"],
    "Epistaxis in Children": ["nosebleed", "bleeding from nose"],
    "Constipation in Children": ["hard stools", "fecal impaction", "encopresis"],
    "Acute Kidney Injury in Children":
        ["AKI", "acute renal failure", "ARF"],
    "ITP":
        ["immune thrombocytopenia", "idiopathic thrombocytopenic purpura",
         "low platelets"],
    "Shock in Office Practice":
        ["shock", "septic shock", "hypovolemic shock", "circulatory shock"],
    "Respiratory Distress in the Term Newborn":
        ["term newborn RDS", "TTN", "term neonate respiratory distress"],
    "Cow's Milk Protein Allergy":
        ["CMPA", "milk allergy", "cow milk allergy"],
    "Myocarditis": ["cardiac inflammation", "viral myocarditis"],
    "Scalds and Burns": ["burns", "scalds", "thermal injury", "Parkland"],
    "Hyperthyroidism": ["Graves disease", "thyrotoxicosis"],
    "Neonatal Jaundice":
        ["jaundice", "hyperbilirubinemia", "phototherapy", "kernicterus"],
    "Autoimmune Encephalitis": ["anti-NMDA encephalitis", "autoimmune brain"],
    "Specific Learning Disorders":
        ["SLD", "dyslexia", "learning disability", "learning disorder"],
    "Puberty": ["precocious puberty", "delayed puberty", "Tanner staging"],
    "Substance Use Disorders in Adolescents":
        ["SUD", "drug use", "addiction", "alcohol abuse"],
    "Rabies Prophylaxis in Children":
        ["rabies", "dog bite", "post-exposure prophylaxis", "PEP"],
    "Oral Thrush": ["candidiasis", "oral candida", "fungal infection mouth"],
    "Scorpion Envenomation":
        ["scorpion sting", "scorpion bite", "prazosin"],
    "Thalassemia":
        ["beta thalassemia", "alpha thalassemia", "transfusion dependent anemia"],
    "Cerebral Palsy": ["CP", "spastic diplegia", "motor disability"],
    "Breath Holding Spell": ["BHS", "breath holding"],
    "Cyanotic Spell": ["tet spell", "hypercyanotic spell", "TOF spell"],
    "Antenatally Detected Hydronephrosis":
        ["ANH", "fetal hydronephrosis", "prenatal hydronephrosis"],
    "GERD":
        ["gastroesophageal reflux", "GORD", "reflux", "gastro-oesophageal reflux"],
    "Anticipatory Guidance in Adolescents":
        ["adolescent counseling", "anticipatory guidance"],
    "Autism Spectrum Disorders": ["ASD", "autism", "autistic"],
    "Malaria": ["plasmodium", "P falciparum", "P vivax"],
    "Social Media Do's and Don'ts":
        ["social media use", "screen time", "internet use"],
    "Approach to Short Stature":
        ["short stature", "growth failure", "GH deficiency"],
    "Feeding in Preterm and Feed Intolerance":
        ["preterm feeding", "feed intolerance", "donor milk", "EBM"],
    "Neurocysticercosis": ["NCC", "cysticercus", "brain tapeworm"],
    "Attention Deficit Hyperactivity Disorder":
        ["ADHD", "hyperactivity", "attention deficit"],
    "Allergic Conjunctivitis":
        ["eye allergy", "vernal keratoconjunctivitis", "VKC"],
    "Snakebite": ["snake bite", "anti-snake venom", "ASV"],
    "Neonatal Cholestasis":
        ["conjugated jaundice", "biliary atresia", "direct hyperbilirubinemia"],
    "Neonatal Resuscitation Program":
        ["NRP", "neonatal resuscitation"],
    "Oxygen Therapy in Office Practice":
        ["O2", "supplemental oxygen", "oxygen delivery"],
    "Staphylococcal Scalded Skin Syndrome":
        ["SSSS", "staph scalded skin"],
    "CTEV and Flat Foot":
        ["CTEV", "club foot", "congenital talipes equinovarus", "pes planus"],
    "Teen Depression and Suicide Prevention":
        ["adolescent depression", "suicide", "mood disorder"],
    "Poisoning in Children":
        ["accidental ingestion", "intoxication", "toxic exposure"],
    "Unprovoked Seizures":
        ["seizure", "epilepsy", "fit", "convulsion"],
    "Paracetamol Poisoning":
        ["acetaminophen poisoning", "paracetamol overdose", "NAC"],
    "Undescended Testes and Testicular Torsion":
        ["cryptorchidism", "testicular torsion", "undescended testes"],
    "Pertussis in Children": ["whooping cough", "pertussis"],
    "Pulled Elbow":
        ["nursemaid elbow", "radial head subluxation"],
    "Dental Caries": ["tooth decay", "cavities", "dental decay"],
    "Stevens-Johnson Syndrome":
        ["SJS", "TEN", "drug reaction"],
    "Acute Dysentery": ["bloody diarrhea", "shigella", "dysentery"],
    "Tinea Infections":
        ["ringworm", "dermatophyte", "fungal skin infection"],
    "Tropical Pulmonary Eosinophilia":
        ["TPE", "pulmonary eosinophilia"],
    "Coping with Stress in Adolescents":
        ["adolescent stress", "mental health", "stress management"],
    "Hyperpigmented Lesions":
        ["hyperpigmentation", "dark spots"],
    "Early Detection and Early Intervention of a High-risk Neonate":
        ["high-risk neonate", "early intervention", "developmental follow up"],
    "Injuries in Office Practice":
        ["minor trauma", "laceration", "minor injury"],
    "Common Worm Infestations":
        ["helminth", "ascaris", "hookworm", "deworming"],
    "Neonatal Seizures": ["newborn seizure", "neonatal convulsion"],
    "Hemophagocytic Lymphohistiocytosis":
        ["HLH", "MAS", "macrophage activation syndrome"],
    "Cleft Lip and Palate": ["cleft", "harelip"],
    "Diphtheria":
        ["corynebacterium", "pseudomembrane"],
    "Traumatic Brain Injury":
        ["TBI", "head injury", "GCS"],
    "Nipah, Zika and Monkeypox":
        ["Nipah", "Zika", "monkeypox"],
    "Encephalitis in Children":
        ["JE", "viral encephalitis", "brain inflammation"],
    "Phimosis": ["tight foreskin", "phimotic"],
    "Influenza in children": ["flu", "H1N1", "seasonal influenza"],
    "Hypospadias": ["hypospadias", "urethral defect"],
    "Severe Acute Malnutrition":
        ["SAM", "malnutrition", "RUTF", "kwashiorkor", "marasmus"],
    "Hypopigmentation":
        ["hypopigmented", "vitiligo", "depigmentation"],
    "Dengue in Children":
        ["dengue fever", "dengue hemorrhagic", "DHF"],
    "Acute Glomerulonephritis":
        ["AGN", "PSGN", "post-strep GN", "hematuria"],
    "Inguinal Hernia and Hydrocele":
        ["hernia", "hydrocele"],
    "Adolescent Sexuality":
        ["sexual health", "adolescent sex education"],
    "Antimicrobial Stewardship in Office Practice":
        ["AMR", "antibiotic resistance", "AMS"],
    "Pediatric Headache":
        ["migraine", "tension headache", "pediatric migraine"],
    "Retinopathy of Prematurity":
        ["ROP", "preterm eye"],
    "Temper Tantrum": ["tantrum", "behavior outburst"],
    "Management of Fever without Focus":
        ["FWF", "fever no focus", "occult bacteremia"],
    "Measles": ["rubeola", "measles vaccine", "MR"],
    "TORCH Infections":
        ["toxoplasma", "rubella", "CMV", "congenital infection"],
    "Diagnosis and Management of Childhood Tuberculosis":
        ["TB", "tuberculosis", "mycobacterium", "ATT"],
    "Management of Cough in Office Practice":
        ["chronic cough", "persistent cough", "productive cough"],
}


def normalise_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    if not INDEX_PATH.exists():
        sys.exit(f"stg_index.json not found at {INDEX_PATH}")

    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    # Build a normalised lookup so casing / punctuation differences don't
    # cause silent misses.
    by_norm = {normalise_title(k): v for k, v in KEYWORDS.items()}

    updated = 0
    no_match = []
    for ch in data["chapters"]:
        title_norm = normalise_title(ch.get("title", ""))
        kws = by_norm.get(title_norm)
        if kws is not None:
            ch["keywords"] = list(kws)
            updated += 1
        else:
            no_match.append(ch.get("title", "(unknown)"))

    INDEX_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Updated keywords on {updated} chapter(s).")
    if no_match:
        print(f"\nNo curated keywords for {len(no_match)} chapter(s) — left "
              f"as-is in stg_index.json:")
        for t in no_match:
            print(f"  · {t}")
    print(f"\nWrote {INDEX_PATH}")
    print("\nNext:\n  git add stg_index.json\n"
          "  git commit -m 'Add curated keywords to STG index'\n"
          "  git push")


if __name__ == "__main__":
    main()
