import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
export const locales = ["fr", "en", "es", "ar"] as const;
export type Locale = typeof locales[number];
export const localeNames: Record<Locale,string> = {fr:"Français",en:"English",es:"Español",ar:"العربية"};
export const isLocale = (value:unknown): value is Locale => typeof value === "string" && locales.some(l=>l===value);
export const direction = (locale:Locale) => locale === "ar" ? "rtl" : "ltr";
const translations = {
fr:{loading:"Chargement…",demo:"Démonstration",logout:"Se déconnecter",loginTitle:"Connexion à ClairTransit",email:"Adresse e-mail",password:"Mot de passe",login:"Se connecter",signingIn:"Connexion…",loginError:"Connexion impossible. Réessayez.",language:"Langue de l'interface"},
en:{loading:"Loading…",demo:"Demo",logout:"Sign out",loginTitle:"Sign in to ClairTransit",email:"Email address",password:"Password",login:"Sign in",signingIn:"Signing in…",loginError:"Unable to sign in. Try again.",language:"Interface language"},
es:{loading:"Cargando…",demo:"Demostración",logout:"Cerrar sesión",loginTitle:"Acceder a ClairTransit",email:"Correo electrónico",password:"Contraseña",login:"Iniciar sesión",signingIn:"Accediendo…",loginError:"No se pudo iniciar sesión.",language:"Idioma de la interfaz"},
ar:{loading:"جارٍ التحميل…",demo:"نسخة تجريبية",logout:"تسجيل الخروج",loginTitle:"تسجيل الدخول إلى ClairTransit",email:"البريد الإلكتروني",password:"كلمة المرور",login:"تسجيل الدخول",signingIn:"جارٍ تسجيل الدخول…",loginError:"تعذر تسجيل الدخول",language:"لغة الواجهة"}
} as const;
export type MessageKey = keyof typeof translations.fr;
type ContextValue={locale:Locale;setLocale:(locale:Locale)=>void;t:(key:MessageKey)=>string};
const Context=createContext<ContextValue|null>(null);
function initialLocale():Locale {try {const v=localStorage.getItem("clairtransit.interface-locale"); if(isLocale(v))return v;}catch{/* blocked */}return "fr";}
export function I18nProvider({children}:{children:ReactNode}){
 const [locale,setLocale]=useState<Locale>(initialLocale);
 useEffect(()=>{document.documentElement.lang=locale;document.documentElement.dir=direction(locale);try{localStorage.setItem("clairtransit.interface-locale",locale);}catch{/* blocked */}},[locale]);
 const value=useMemo<ContextValue>(()=>({locale,setLocale,t:(key)=>translations[locale][key]}),[locale]);
 return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useI18n(){const value=useContext(Context);if(!value)throw Error("Missing I18nProvider");return value;}
export function LanguageSelector(){const {locale,setLocale,t}=useI18n();return <label className="inline"><span className="visually-hidden">{t("language")}</span><select aria-label={t("language")} value={locale} onChange={e=>setLocale(e.target.value as Locale)}>{locales.map(l=><option key={l} value={l}>{localeNames[l]}</option>)}</select></label>;}
