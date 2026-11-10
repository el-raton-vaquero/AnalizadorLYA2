int a = 5;
int b = 10;
int c = a + b;
int total = 0;
int i = 1;
while (i <= 3) {
    total = total + c;
    i = i + 1;
}
if (total > 20) {
    cout << total;
}
