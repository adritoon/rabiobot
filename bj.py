import tkinter as tk
from tkinter import simpledialog, messagebox, font

# --- LÓGICA DE BLACKJACK (Sin cambios) ---
# [Se omite por brevedad, es la misma lógica de cálculo de valor y estrategia]
def calcular_valor(mano):
    valor = 0
    num_ases = 0
    for carta in mano:
        rank = carta[0]
        if rank.isdigit():
            valor += int(rank)
        elif rank in ['J', 'Q', 'K']:
            valor += 10
        elif rank == 'A':
            num_ases += 1
            valor += 11
    while valor > 21 and num_ases > 0:
        valor -= 10
        num_ases -= 1
    return valor

def obtener_estrategia(mano_jugador, carta_crupier):
    valor_jugador = calcular_valor(mano_jugador)
    valor_crupier_visible = calcular_valor([carta_crupier])
    es_primera_jugada = len(mano_jugador) == 2
    if es_primera_jugada and mano_jugador[0][0] == mano_jugador[1][0]:
        par = mano_jugador[0][0]
        if par in ['A', '8']: return "Dividir (Split)"
        if par in ['10', 'J', 'Q', 'K']: return "Plantarse (Stand)"
        if par == '9' and valor_crupier_visible not in [7, 10, 11]: return "Dividir (Split)"
        if par == '7' and valor_crupier_visible <= 7: return "Dividir (Split)"
        if par == '6' and valor_crupier_visible <= 6: return "Dividir (Split)"
        if par == '5' and valor_crupier_visible <= 9: return "Doblar (Double Down)"
        if par == '4' and valor_crupier_visible in [5, 6]: return "Dividir (Split)"
        if par in ['2', '3'] and valor_crupier_visible <= 7: return "Dividir (Split)"
    es_mano_suave = 'A' in [c[0] for c in mano_jugador] and calcular_valor([c for c in mano_jugador if c[0] != 'A']) + 11 == valor_jugador
    if es_mano_suave:
        if valor_jugador >= 19: return "Plantarse (Stand)"
        if valor_jugador == 18:
            return "Doblar (Double Down)" if es_primera_jugada and valor_crupier_visible <= 8 else "Plantarse (Stand)"
        if valor_jugador == 17:
            return "Doblar (Double Down)" if es_primera_jugada and 3 <= valor_crupier_visible <= 6 else "Pedir (Hit)"
        if valor_jugador in [15, 16]:
            return "Doblar (Double Down)" if es_primera_jugada and 4 <= valor_crupier_visible <= 6 else "Pedir (Hit)"
        if valor_jugador in [13, 14]:
            return "Doblar (Double Down)" if es_primera_jugada and 5 <= valor_crupier_visible <= 6 else "Pedir (Hit)"
    if valor_jugador >= 17: return "Plantarse (Stand)"
    if 13 <= valor_jugador <= 16:
        return "Plantarse (Stand)" if valor_crupier_visible <= 6 else "Pedir (Hit)"
    if valor_jugador == 12:
        return "Plantarse (Stand)" if 4 <= valor_crupier_visible <= 6 else "Pedir (Hit)"
    if valor_jugador == 11:
        return "Doblar (Double Down)" if es_primera_jugada else "Pedir (Hit)"
    if valor_jugador == 10:
        return "Doblar (Double Down)" if es_primera_jugada and valor_crupier_visible <= 9 else "Pedir (Hit)"
    if valor_jugador == 9:
        return "Doblar (Double Down)" if es_primera_jugada and 3 <= valor_crupier_visible <= 6 else "Pedir (Hit)"
    return "Pedir (Hit)"

# --- CLASE DE LA APLICACIÓN GRÁFICA MEJORADA ---

class BlackjackAdvisorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Asesor de Blackjack Pro")
        self.root.geometry("600x800")
        self.root.resizable(False, False)

        # Paletas de colores
        self.colors = {
            "dark": {"bg": "#2E2E2E", "fg": "#EAEAEA", "frame_bg": "#3C3C3C", "button_bg": "#505050", "consejo_fg": "#40E0D0"},
            "light": {"bg": "#F0F0F0", "fg": "#000000", "frame_bg": "#E0E0E0", "button_bg": "#FFFFFF", "consejo_fg": "blue"}
        }
        self.is_dark_mode = tk.BooleanVar(value=False)

        # Estilos y fuentes
        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font.configure(family="Segoe UI", size=10)
        self.title_font = ("Segoe UI", 16, "bold")
        self.label_font = ("Segoe UI", 12)
        self.consejo_font = ("Segoe UI", 14, "bold")
        
        # Variables de estado del juego
        self.capital = tk.DoubleVar()
        self.apuesta = tk.DoubleVar()
        self.ultima_apuesta = 0
        self.mano_jugador = []
        self.mano_crupier = []
        # Para Splits
        self.mano_dividida_2 = []
        self.mano_activa = 1 # 1 para principal, 2 para dividida
        
        self.estado_juego = "INICIO"
        self.widgets = [] # Para guardar todos los widgets y cambiarles el color

        self.setup_ui()
        self.get_initial_capital()
        self.toggle_dark_mode() # Aplicar tema inicial

    def setup_ui(self):
        self.main_frame = tk.Frame(self.root, padx=15, pady=15)
        self.main_frame.pack(fill="both", expand=True)
        self.widgets.append(self.main_frame)

        # --- Fila Superior: Título y Modo Oscuro ---
        top_frame = tk.Frame(self.main_frame)
        top_frame.pack(fill="x", pady=5)
        self.widgets.append(top_frame)
        
        title_label = tk.Label(top_frame, text="Asesor de Blackjack", font=self.title_font)
        title_label.pack(side="left", expand=True)
        self.widgets.append(title_label)
        
        dark_mode_switch = tk.Checkbutton(top_frame, text="Modo Oscuro", variable=self.is_dark_mode, command=self.toggle_dark_mode)
        dark_mode_switch.pack(side="right")
        self.widgets.append(dark_mode_switch)

        # --- Sección de Banca ---
        banca_frame = tk.LabelFrame(self.main_frame, text="Banca", font=self.title_font, padx=10, pady=10)
        banca_frame.pack(fill="x", pady=5)
        self.widgets.append(banca_frame)
        
        l1 = tk.Label(banca_frame, text="Capital Actual:", font=self.label_font); l1.grid(row=0, column=0, sticky="w")
        self.capital_label = tk.Label(banca_frame, textvariable=self.capital, font=("Segoe UI", 12, "bold")); self.capital_label.grid(row=0, column=1, sticky="w")
        l2 = tk.Label(banca_frame, text="Apuesta:", font=self.label_font); l2.grid(row=1, column=0, sticky="w")
        self.apuesta_label = tk.Label(banca_frame, textvariable=self.apuesta, font=("Segoe UI", 12, "bold")); self.apuesta_label.grid(row=1, column=1, sticky="w")
        self.widgets.extend([l1, self.capital_label, l2, self.apuesta_label])

        # --- Sección de la Mesa ---
        mesa_frame = tk.LabelFrame(self.main_frame, text="Mesa", font=self.title_font, padx=10, pady=10)
        mesa_frame.pack(fill="x", pady=10)
        self.widgets.append(mesa_frame)
        
        l3 = tk.Label(mesa_frame, text="Tus Cartas:", font=self.label_font); l3.grid(row=0, column=0, sticky="w")
        self.jugador_cartas_label = tk.Label(mesa_frame, text="[]", font=self.label_font); self.jugador_cartas_label.grid(row=0, column=1, sticky="w", columnspan=2)
        l4 = tk.Label(mesa_frame, text="Carta Crupier:", font=self.label_font); l4.grid(row=1, column=0, sticky="w")
        self.crupier_carta_label = tk.Label(mesa_frame, text="[]", font=self.label_font); self.crupier_carta_label.grid(row=1, column=1, sticky="w")
        self.widgets.extend([l3, self.jugador_cartas_label, l4, self.crupier_carta_label])
        
        # --- Sección de Consejos ---
        consejo_frame = tk.Frame(self.main_frame, pady=10)
        consejo_frame.pack(fill="x")
        self.widgets.append(consejo_frame)
        self.info_label = tk.Label(consejo_frame, text="Bienvenido. Inicia una nueva mano.", font=self.label_font, wraplength=550)
        self.info_label.pack()
        self.consejo_label = tk.Label(consejo_frame, text="", font=self.consejo_font)
        self.consejo_label.pack(pady=10)
        self.widgets.extend([self.info_label, self.consejo_label])

        # --- Teclado de Cartas ---
        self.teclado_frame = tk.Frame(self.main_frame, pady=10)
        self.teclado_frame.pack()
        self.widgets.append(self.teclado_frame)
        cartas = ['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2']
        self.botones_cartas = {}
        for i, carta in enumerate(cartas):
            row, col = divmod(i, 7)
            btn = tk.Button(self.teclado_frame, text=carta, width=5, height=2, command=lambda c=carta: self.carta_presionada(c))
            btn.grid(row=row, column=col, padx=2, pady=2)
            self.botones_cartas[carta] = btn
            self.widgets.append(btn)

        # --- Botones de Acción ---
        self.acciones_frame = tk.Frame(self.main_frame, pady=10)
        self.acciones_frame.pack()
        self.widgets.append(self.acciones_frame)
        self.boton_pedir = tk.Button(self.acciones_frame, text="Pedí Carta (Hit)", command=self.pedir_carta, state="disabled", height=2)
        self.boton_pedir.pack(side="left", padx=5)
        self.boton_plantarse = tk.Button(self.acciones_frame, text="Me Planté (Stand)", command=self.plantarse, state="disabled", height=2)
        self.boton_plantarse.pack(side="left", padx=5)
        self.boton_doblar = tk.Button(self.acciones_frame, text="Doblé (Double)", command=self.doblar, state="disabled", height=2)
        self.boton_doblar.pack(side="left", padx=5)
        self.boton_dividir = tk.Button(self.acciones_frame, text="Dividí (Split)", command=self.dividir, state="disabled", height=2)
        self.boton_dividir.pack(side="left", padx=5)
        self.widgets.extend([self.boton_pedir, self.boton_plantarse, self.boton_doblar, self.boton_dividir])
        
        self.boton_nueva_mano = tk.Button(self.main_frame, text="Iniciar Nueva Mano", command=self.iniciar_nueva_mano, height=2, width=20)
        self.boton_nueva_mano.pack(pady=20)
        self.widgets.append(self.boton_nueva_mano)
        
    # --- LÓGICA DE LA INTERFAZ ---

    def toggle_dark_mode(self):
        mode = "dark" if self.is_dark_mode.get() else "light"
        colors = self.colors[mode]
        self.root.config(bg=colors["bg"])

        for widget in self.widgets:
            widget_class = widget.winfo_class()
            
            # Primero, intenta aplicar configuraciones comunes
            try:
                widget.config(bg=colors["bg"], fg=colors["fg"])
            except tk.TclError:
                # Si falla (porque no tiene 'fg'), solo aplica 'bg'
                widget.config(bg=colors["bg"])
            
            # Aplicar estilos específicos por tipo de widget
            if widget_class == "Labelframe":
                widget.config(bg=colors["frame_bg"])
            elif widget_class == "Button":
                widget.config(bg=colors["button_bg"], activebackground=colors["fg"], activeforeground=colors["button_bg"])
            elif widget_class == "TCheckbutton": # Para el checkbox del modo oscuro
                widget.config(bg=colors["bg"])

        # Finalmente, el color especial del consejo
        self.consejo_label.config(fg=colors["consejo_fg"], bg=colors["bg"])


    def get_initial_capital(self):
        capital_inicial = simpledialog.askinteger("Capital Inicial", "Introduce tu capital inicial:", parent=self.root, minvalue=1)
        self.capital.set(float(capital_inicial) if capital_inicial else 1000.0)
        self.ultima_apuesta = int(self.capital.get() * 0.01) # Sugerencia inicial
    
    def iniciar_nueva_mano(self):
        prompt = f"Capital: {self.capital.get():.2f}\nSugerencia: {self.ultima_apuesta}\n\n¿Cuánto apuestas?"
        apuesta = simpledialog.askinteger("Nueva Apuesta", prompt, parent=self.root, initialvalue=self.ultima_apuesta, minvalue=1, maxvalue=int(self.capital.get()))
        if not apuesta: return
        
        self.apuesta.set(float(apuesta))
        self.ultima_apuesta = apuesta
        self.mano_jugador, self.mano_crupier, self.mano_dividida_2 = [], [], []
        self.mano_activa = 1
        self.consejo_label.config(text="")
        
        self.boton_nueva_mano.pack_forget()
        self.toggle_botones_cartas("normal")
        self.toggle_botones_accion("disabled")

        self.estado_juego = "JUGADOR_C1"
        self.info_label.config(text="Introduce tu PRIMERA carta:")
        self.actualizar_display()

    def carta_presionada(self, carta):
        mano_actual = self.mano_jugador if self.mano_activa == 1 else self.mano_dividida_2
        
        if self.estado_juego == "JUGADOR_C1":
            self.mano_jugador.append((carta, '♠'))
            self.estado_juego = "JUGADOR_C2"
            self.info_label.config(text="Introduce tu SEGUNDA carta:")
        elif self.estado_juego == "JUGADOR_C2":
            self.mano_jugador.append((carta, '♠'))
            self.estado_juego = "CRUPIER_C1"
            self.info_label.config(text="Introduce la carta VISIBLE del crupier:")
        elif self.estado_juego == "CRUPIER_C1":
            self.mano_crupier.append((carta, '♠'))
            self.estado_juego = "JUGANDO"
            self.info_label.config(text="Sigue el consejo o tu jugada.")
            self.toggle_botones_cartas("disabled")
            self.toggle_botones_accion("normal")
        elif self.estado_juego == "PIDIENDO":
            mano_actual.append((carta, '♠'))
            self.estado_juego = "JUGANDO"
            self.info_label.config(text="Sigue el consejo o tu jugada.")
            self.toggle_botones_cartas("disabled")
            self.toggle_botones_accion("normal")
        elif self.estado_juego == "DOBLANDO":
            self.mano_jugador.append((carta, '♠'))
            self.plantarse() # Doblar fuerza a plantarse
        elif self.estado_juego == "DIVIDIENDO":
            mano_actual.append((carta, '♠'))
            self.estado_juego = "JUGANDO"
            self.info_label.config(text=f"Jugando MANO {self.mano_activa}. Sigue el consejo.")
            self.toggle_botones_cartas("disabled")
            self.toggle_botones_accion("normal", split=True)

        self.actualizar_display()
    
    def pedir_carta(self):
        self.estado_juego = "PIDIENDO"
        self.info_label.config(text="¿Qué nueva carta has recibido?")
        self.toggle_botones_cartas("normal")
        self.toggle_botones_accion("disabled")

    def plantarse(self):
        # Si estábamos jugando la mano 1 de un split, pasamos a la mano 2
        if self.mano_dividida_2 and self.mano_activa == 1:
            self.mano_activa = 2
            self.estado_juego = "DIVIDIENDO"
            self.info_label.config(text=f"Ahora juega la MANO 2. Introduce su segunda carta:")
            self.toggle_botones_cartas("normal")
            self.toggle_botones_accion("disabled")
            self.actualizar_display()
        else: # Si no, la jugada termina
            self.estado_juego = "RESULTADO"
            self.info_label.config(text="La mano ha terminado. Registra el resultado final.")
            self.toggle_botones_cartas("disabled")
            self.toggle_botones_accion("disabled")
            self.mostrar_ventana_resultado()

    def doblar(self):
        self.apuesta.set(self.apuesta.get() * 2)
        self.estado_juego = "DOBLANDO"
        self.info_label.config(text="Introduce la ÚNICA carta adicional que recibiste:")
        self.toggle_botones_cartas("normal")
        self.toggle_botones_accion("disabled")

    def dividir(self):
        if self.capital.get() < self.apuesta.get() * 2:
            messagebox.showwarning("Capital Insuficiente", "No tienes suficiente capital para dividir.")
            return
        
        # Prepara las dos manos
        self.mano_dividida_2 = [self.mano_jugador.pop(1)]
        self.mano_activa = 1
        
        self.estado_juego = "DIVIDIENDO"
        self.info_label.config(text="Mano dividida. Introduce la segunda carta de la MANO 1:")
        self.toggle_botones_cartas("normal")
        self.toggle_botones_accion("disabled")
        self.actualizar_display()

    def actualizar_display(self):
        # Muestra las cartas
        if not self.mano_dividida_2:
            self.jugador_cartas_label.config(text=f"{' '.join([c[0] for c in self.mano_jugador])}  (Valor: {calcular_valor(self.mano_jugador)})")
        else:
            mano1_str = f"Mano 1: {' '.join([c[0] for c in self.mano_jugador])} (V: {calcular_valor(self.mano_jugador)})"
            mano2_str = f"Mano 2: {' '.join([c[0] for c in self.mano_dividida_2])} (V: {calcular_valor(self.mano_dividida_2)})"
            self.jugador_cartas_label.config(text=f"{mano1_str}\n{mano2_str}")
        
        self.crupier_carta_label.config(text=f"{self.mano_crupier[0][0] if self.mano_crupier else ''}")

        # Da el consejo si el juego está en curso
        if self.estado_juego == "JUGANDO":
            mano_actual = self.mano_jugador if self.mano_activa == 1 else self.mano_dividida_2
            if calcular_valor(mano_actual) >= 21:
                self.consejo_label.config(text="Automáticamente te plantas o pierdes", fg="red")
                self.plantarse() # Pasa a la siguiente fase
            else:
                consejo = obtener_estrategia(mano_actual, self.mano_crupier[0])
                self.consejo_label.config(text=f"Consejo: {consejo}")
    
    def toggle_botones_cartas(self, estado="normal"):
        for btn in self.botones_cartas.values():
            btn.config(state=estado)
    
    def toggle_botones_accion(self, estado="normal", split=False):
        es_primera_jugada = len(self.mano_jugador) == 2 and not self.mano_dividida_2
        self.boton_pedir.config(state=estado)
        self.boton_plantarse.config(state=estado)
        self.boton_doblar.config(state=estado if es_primera_jugada and not split else "disabled")
        self.boton_dividir.config(state=estado if es_primera_jugada and self.mano_jugador[0][0] == self.mano_jugador[1][0] else "disabled")

    def mostrar_ventana_resultado(self):
        # Crear una nueva ventana Toplevel para los resultados
        self.result_window = tk.Toplevel(self.root)
        self.result_window.title("Resultado de la Mano")
        self.result_window.transient(self.root) # Mantenerla encima de la principal
        self.result_window.grab_set() # Bloquear la ventana principal

        if not self.mano_dividida_2: # Mano normal
            tk.Label(self.result_window, text="¿Cuál fue el resultado?", font=self.label_font).pack(pady=10)
            btn_frame = tk.Frame(self.result_window)
            btn_frame.pack(pady=10, padx=10)
            tk.Button(btn_frame, text="Gané", command=lambda: self.registrar_resultado("G")).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Perdí", command=lambda: self.registrar_resultado("P")).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Empaté", command=lambda: self.registrar_resultado("E")).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Gané con Blackjack", command=lambda: self.registrar_resultado("B")).pack(side="left", padx=5)
        else: # Mano dividida
            self.res_mano1 = tk.StringVar(value="P")
            self.res_mano2 = tk.StringVar(value="P")
            
            # Resultado Mano 1
            f1 = tk.LabelFrame(self.result_window, text="Mano 1", padx=10, pady=10)
            f1.pack(pady=5, padx=10)
            opciones = [("Gané", "G"), ("Perdí", "P"), ("Empaté", "E")]
            for texto, valor in opciones:
                tk.Radiobutton(f1, text=texto, variable=self.res_mano1, value=valor).pack(side="left")

            # Resultado Mano 2
            f2 = tk.LabelFrame(self.result_window, text="Mano 2", padx=10, pady=10)
            f2.pack(pady=5, padx=10)
            for texto, valor in opciones:
                tk.Radiobutton(f2, text=texto, variable=self.res_mano2, value=valor).pack(side="left")

            tk.Button(self.result_window, text="Confirmar Resultados", command=self.registrar_split_resultado).pack(pady=15)
        
    def registrar_resultado(self, resultado):
        if hasattr(self, 'result_window'): self.result_window.destroy()
        
        apuesta_actual = self.apuesta.get()
        capital_actual = self.capital.get()
        
        if resultado == "G": self.capital.set(capital_actual + apuesta_actual)
        elif resultado == "P": self.capital.set(capital_actual - apuesta_actual)
        elif resultado == "B": self.capital.set(capital_actual + (apuesta_actual * 1.5))
        
        self.finalizar_mano()

    def registrar_split_resultado(self):
        self.result_window.destroy()
        apuesta_por_mano = self.apuesta.get()
        capital_actual = self.capital.get()
        
        resultados = [self.res_mano1.get(), self.res_mano2.get()]
        ganancia_neta = 0

        for res in resultados:
            if res == "G": ganancia_neta += apuesta_por_mano
            elif res == "P": ganancia_neta -= apuesta_por_mano
        
        self.capital.set(capital_actual + ganancia_neta)
        self.finalizar_mano()

    def finalizar_mano(self):
        if self.capital.get() <= 0:
            messagebox.showinfo("Fin del Juego", "Te has quedado sin capital.")
            self.root.destroy()
        else:
            self.boton_nueva_mano.pack(pady=20)
            self.info_label.config(text="Mano terminada. Inicia una nueva.")

if __name__ == "__main__":
    root = tk.Tk()
    app = BlackjackAdvisorApp(root)
    root.mainloop()