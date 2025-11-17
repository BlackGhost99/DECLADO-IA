/**
 * Module d'extraction des données de factures commerciales
 * Supporte les formats PDF et images (JPG, PNG)
 */
class InvoiceExtractor {
    constructor() {
        this.requiredFields = [
            'numeroFacture',
            'dateFacture',
            'fournisseur',
            'destinataire',
            'montantTotal',
            'devise',
            'articles'
        ];
    }

    /**
     * Extrait les données d'une facture
     * @param {string} filePath - Chemin du fichier
     * @param {string} fileData - Données du fichier en base64
     * @returns {Object} - Données extraites de la facture
     */
    async extract(filePath, fileData) {
        const fileExtension = filePath.split('.').pop().toLowerCase();

        try {
            // Pour cette version, on simule l'extraction avec des données d'exemple
            // Dans une version complète, on utiliserait Tesseract.js ou pdf-parse
            return this.extractSimulated(filePath);
        } catch (error) {
            throw new Error(`Erreur lors de l'extraction de la facture: ${error.message}`);
        }
    }

    /**
     * Simulation de l'extraction pour démonstration
     * Dans une version production, ceci serait remplacé par un vrai OCR
     */
    extractSimulated(filePath) {
        // Données simulées pour démonstration
        return {
            numeroFacture: 'FAC-2024-' + Math.floor(Math.random() * 10000),
            dateFacture: new Date().toISOString().split('T')[0],
            fournisseur: {
                nom: 'Société Exportatrice International',
                adresse: '123 Rue du Commerce, Paris, France',
                telephone: '+33 1 23 45 67 89',
                email: 'contact@exportateur.fr'
            },
            destinataire: {
                nom: 'Entreprise Importatrice CEMAC',
                adresse: 'BP 456, Yaoundé, Cameroun',
                telephone: '+237 222 33 44 55',
                email: 'import@entreprise.cm'
            },
            articles: [
                {
                    description: 'Matériel informatique - Ordinateurs portables',
                    quantite: 50,
                    prixUnitaire: 800000,
                    montantTotal: 40000000,
                    origine: 'France',
                    codeHS: '8471.30.00'
                },
                {
                    description: 'Équipements de bureau',
                    quantite: 100,
                    prixUnitaire: 150000,
                    montantTotal: 15000000,
                    origine: 'France',
                    codeHS: '9403.30.00'
                }
            ],
            montantTotal: 55000000, // XAF
            devise: 'XAF',
            conditions: 'FOB',
            incoterm: 'CIF',
            fichierSource: filePath.split('/').pop()
        };
    }

    /**
     * Valide les données extraites
     */
    validate(data) {
        const missingFields = [];
        
        for (const field of this.requiredFields) {
            if (!data[field]) {
                missingFields.push(field);
            }
        }

        if (missingFields.length > 0) {
            throw new Error(`Champs manquants: ${missingFields.join(', ')}`);
        }

        return true;
    }

    /**
     * Calcule le montant FOB total
     */
    calculateFOB(data) {
        if (data.articles && Array.isArray(data.articles)) {
            return data.articles.reduce((total, article) => total + article.montantTotal, 0);
        }
        return data.montantTotal || 0;
    }
}

module.exports = InvoiceExtractor;
