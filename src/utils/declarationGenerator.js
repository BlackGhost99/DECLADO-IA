/**
 * Générateur de déclarations douanières pour la zone CEMAC
 */
class DeclarationGenerator {
    constructor() {
        this.version = '1.0.0';
        this.systemName = 'Système de Déclaration Douanière CEMAC';
    }

    /**
     * Génère une déclaration douanière complète
     * @param {Object} invoiceData - Données de la facture
     * @param {Object} transportData - Données de transport
     * @param {Object} insuranceData - Données d'assurance
     * @param {Object} taxData - Données des taxes calculées
     * @returns {Object} - Déclaration complète
     */
    generate(invoiceData, transportData, insuranceData, taxData) {
        const declarationNumber = this.generateDeclarationNumber();
        const timestamp = new Date().toISOString();

        return {
            // En-tête de la déclaration
            declaration: {
                numero: declarationNumber,
                dateCreation: timestamp,
                type: 'DECLARATION_IMPORTATION',
                regime: 'MISE_A_LA_CONSOMMATION',
                bureau: 'CEMAC',
                statut: 'BROUILLON',
                systeme: {
                    nom: this.systemName,
                    version: this.version
                }
            },

            // Informations de l'importateur
            importateur: invoiceData.destinataire,

            // Informations de l'exportateur
            exportateur: invoiceData.fournisseur,

            // Détails des marchandises
            marchandises: this.formatMarchandises(invoiceData),

            // Informations de transport
            transport: transportData ? {
                mode: transportData.modeTransport,
                numeroConnaissement: transportData.numeroConnaissement,
                transporteur: transportData.transporteur.nom,
                portDepart: transportData.portDepart,
                portArrivee: transportData.portArrivee,
                dateArrivee: transportData.dateArrivee,
                coutTotal: transportData.montantTotal
            } : null,

            // Informations d'assurance
            assurance: insuranceData ? {
                numeroPolice: insuranceData.numeroPolice,
                assureur: insuranceData.assureur.nom,
                typeAssurance: insuranceData.typeAssurance,
                montantPrime: insuranceData.primeAssurance
            } : null,

            // Valorisation douanière
            valorisation: {
                valeurFOB: taxData.fobValue,
                fret: taxData.freight,
                assurance: taxData.insurance,
                valeurCIF: taxData.cifValue,
                devise: taxData.currency
            },

            // Liquidation des droits et taxes
            liquidation: {
                droitsDeDouane: {
                    base: taxData.cifValue,
                    taux: taxData.customsDutyRate,
                    montant: taxData.customsDuty
                },
                tva: {
                    base: taxData.cifValue + taxData.customsDuty,
                    taux: taxData.vatRate,
                    montant: taxData.vat
                },
                tci: {
                    base: taxData.cifValue,
                    taux: taxData.tciRate,
                    montant: taxData.tci
                },
                redevanceStatistique: {
                    base: taxData.cifValue,
                    taux: taxData.statisticalFeeRate,
                    montant: taxData.statisticalFee
                },
                totalAPayer: taxData.total
            },

            // Détail du calcul
            detailCalcul: taxData.breakdown,

            // Documents joints
            documentsJoints: this.listDocuments(invoiceData, transportData, insuranceData),

            // Résumé pour validation
            resume: {
                nombreArticles: invoiceData.articles ? invoiceData.articles.length : 0,
                valeurTotaleCIF: taxData.cifValue,
                totalDroitsEtTaxes: taxData.total,
                montantTotal: taxData.cifValue + taxData.total,
                devise: 'XAF'
            },

            // Métadonnées
            metadata: {
                dateGeneration: timestamp,
                genereParSysteme: this.systemName,
                modeHorsLigne: true,
                version: this.version
            }
        };
    }

    /**
     * Génère un numéro de déclaration unique
     */
    generateDeclarationNumber() {
        const year = new Date().getFullYear();
        const month = String(new Date().getMonth() + 1).padStart(2, '0');
        const random = Math.floor(Math.random() * 100000).toString().padStart(5, '0');
        return `CEMAC-${year}${month}-${random}`;
    }

    /**
     * Formate les informations des marchandises
     */
    formatMarchandises(invoiceData) {
        if (!invoiceData.articles || invoiceData.articles.length === 0) {
            return [];
        }

        return invoiceData.articles.map((article, index) => ({
            numero: index + 1,
            codeHS: article.codeHS,
            description: article.description,
            origine: article.origine,
            quantite: article.quantite,
            prixUnitaire: article.prixUnitaire,
            montantTotal: article.montantTotal,
            devise: invoiceData.devise
        }));
    }

    /**
     * Liste les documents joints à la déclaration
     */
    listDocuments(invoiceData, transportData, insuranceData) {
        const documents = [];

        if (invoiceData && invoiceData.fichierSource) {
            documents.push({
                type: 'FACTURE_COMMERCIALE',
                obligatoire: true,
                fichier: invoiceData.fichierSource,
                statut: 'PRESENTE'
            });
        }

        if (transportData && transportData.fichierSource) {
            documents.push({
                type: 'CONNAISSEMENT',
                obligatoire: false,
                fichier: transportData.fichierSource,
                statut: 'PRESENTE'
            });
        }

        if (insuranceData && insuranceData.fichierSource) {
            documents.push({
                type: 'POLICE_ASSURANCE',
                obligatoire: false,
                fichier: insuranceData.fichierSource,
                statut: 'PRESENTE'
            });
        }

        // Documents requis non présentés
        const requiredDocs = [
            { type: 'CERTIFICAT_ORIGINE', obligatoire: true },
            { type: 'LISTE_COLISAGE', obligatoire: true },
            { type: 'AUTORISATION_IMPORTATION', obligatoire: false }
        ];

        for (const doc of requiredDocs) {
            documents.push({
                ...doc,
                statut: 'NON_PRESENTE'
            });
        }

        return documents;
    }

    /**
     * Génère un rapport PDF (simulation)
     */
    generatePDF(declaration) {
        // Dans une version complète, on utiliserait pdfkit ou jsPDF
        return {
            format: 'PDF',
            titre: `Déclaration Douanière ${declaration.declaration.numero}`,
            contenu: JSON.stringify(declaration, null, 2),
            dateGeneration: new Date().toISOString()
        };
    }

    /**
     * Valide la déclaration avant export
     */
    validate(declaration) {
        const errors = [];
        const warnings = [];

        // Vérifications obligatoires
        if (!declaration.importateur) {
            errors.push('Informations importateur manquantes');
        }

        if (!declaration.exportateur) {
            errors.push('Informations exportateur manquantes');
        }

        if (!declaration.marchandises || declaration.marchandises.length === 0) {
            errors.push('Aucune marchandise déclarée');
        }

        // Vérifications optionnelles
        if (!declaration.transport) {
            warnings.push('Informations de transport non fournies');
        }

        if (!declaration.assurance) {
            warnings.push('Informations d\'assurance non fournies');
        }

        // Vérifier que les montants sont cohérents
        if (declaration.liquidation.totalAPayer <= 0) {
            warnings.push('Le montant total des taxes est nul ou négatif');
        }

        return {
            valide: errors.length === 0,
            erreurs: errors,
            avertissements: warnings
        };
    }

    /**
     * Exporte la déclaration en différents formats
     */
    export(declaration, format = 'JSON') {
        const validation = this.validate(declaration);

        if (!validation.valide) {
            throw new Error(`La déclaration contient des erreurs: ${validation.erreurs.join(', ')}`);
        }

        switch (format.toUpperCase()) {
            case 'JSON':
                return JSON.stringify(declaration, null, 2);
            case 'PDF':
                return this.generatePDF(declaration);
            case 'XML':
                return this.generateXML(declaration);
            default:
                throw new Error(`Format non supporté: ${format}`);
        }
    }

    /**
     * Génère un export XML (simulation)
     */
    generateXML(declaration) {
        // Simplification pour la démo
        return `<?xml version="1.0" encoding="UTF-8"?>
<DeclarationDouaniereCEMAC>
    <Numero>${declaration.declaration.numero}</Numero>
    <Date>${declaration.declaration.dateCreation}</Date>
    <ValeurCIF>${declaration.valorisation.valeurCIF}</ValeurCIF>
    <TotalTaxes>${declaration.liquidation.totalAPayer}</TotalTaxes>
</DeclarationDouaniereCEMAC>`;
    }
}

module.exports = DeclarationGenerator;
