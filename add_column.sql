-- Script SQL pour ajouter la colonne moyenne_avec_coefficient
-- À exécuter dans votre base de données PostgreSQL

-- Vérifier si la colonne existe
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='school_admin_moyenneperiode' 
AND column_name='moyenne_avec_coefficient';

-- Si la colonne n'existe pas, exécuter cette commande:
ALTER TABLE school_admin_moyenneperiode 
ADD COLUMN IF NOT EXISTS moyenne_avec_coefficient NUMERIC(8, 2) NULL;

-- Vérification finale
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns 
WHERE table_name='school_admin_moyenneperiode' 
AND column_name='moyenne_avec_coefficient';

