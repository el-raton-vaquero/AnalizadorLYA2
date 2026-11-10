#include <iostream>

class CodigoIntermedio {
public:
    static int ejecutar() {
        int a = 5;
        int b = 10;
        int t1 = a + b;
        int t2 = a + b;
        int x;
        if (t1 > 10) {
            x = 1;
        } else {
            x = 0;
        }
        int y = x;
        int z = 20 + 30;
        int w = 100;
        return y;
        // Código inalcanzable:
        // w = 200;
    }
};

int main() {
    std::cout << CodigoIntermedio::ejecutar() << std::endl;
    return 0;
}
