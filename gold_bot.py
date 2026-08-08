from signal_writer import write_signal

def send_trend_message():
    message = "Trend: Yükseliş"
    send_message(message)      
    write_signal("YUKSELIS")   
