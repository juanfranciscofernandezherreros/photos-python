import argparse
from scapy.all import Ether, ARP, srp

def arp_scan(ip):
    """
    Escanea la red enviando peticiones ARP a un rango de direcciones IP.
    """
    # Crea el paquete ARP encapsulado en una trama Ethernet de difusión (broadcast)
    request = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
    
    # Envía los paquetes y espera las respuestas (verbose=0 oculta el texto de depuración)
    ans, unans = srp(request, timeout=2, retry=1, verbose=0)
    
    result = []
    for sent, received in ans:
        result.append({'IP': received.psrc, 'MAC': received.hwsrc})
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Lista los dispositivos en la red local.")
    parser.add_argument(
        'IP', 
        help='El rango de red a escanear (ejemplo: 192.168.1.0/24)'
    )
    args = parser.parse_args()

    dispositivos = arp_scan(args.IP)

    print("Dirección IP\t\tDirección MAC")
    print("-" * 45)
    for dispositivo in dispositivos:
        print(f"{dispositivo['IP']}\t\t{dispositivo['MAC']}")

if __name__ == '__main__':
    main()