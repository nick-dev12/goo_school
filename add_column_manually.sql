-- Script SQL pour ajouter la colonne moyenne_avec_coefficient manuellement
-- À exécuter dans la base de données PostgreSQL

ALTER TABLE school_admin_moyenneperiode 
ADD COLUMN moyenne_avec_coefficient NUMERIC(8, 2) NULL;

COMMENT ON COLUMN school_admin_moyenneperiode.moyenne_avec_coefficient IS 'Moyenne de l''élève multipliée par le coefficient de la matière';

