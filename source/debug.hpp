
namespace debug {

    unsigned long findmin_reads {0};
    unsigned long readmin_reads {0};
    unsigned long intersect_reads {0};
    unsigned long hashtovid_reads {0};
    unsigned long verify_reads {0};
    
    unsigned long indexed_tables {0};
    unsigned long indexing_tables {0};

    unsigned long solution_correct {0};
    unsigned long solution_wrong {0};

    unsigned long intersect_sol_truepositive {0};
    unsigned long intersect_sol_truenegative {0};
    unsigned long intersect_sol_falsepositive {0};
    unsigned long intersect_sol_falsenegative {0};
    unsigned long intersect_bit_truepositive {0};
    unsigned long intersect_bit_truenegative {0};
    unsigned long intersect_bit_falsepositive {0};
    unsigned long intersect_bit_falsenegative {0};
    
    unsigned long verify_reusage {0};
    unsigned long embeddings {0};
    unsigned long max_collisions {0};
    float avg_collisions {0};

    static void init(){
        findmin_reads  = 0;
        readmin_reads  = 0;
        intersect_reads  = 0;
        hashtovid_reads  = 0;
        verify_reads  = 0;
        indexed_tables  = 0;
        indexing_tables  = 0;
        solution_correct  = 0;
        solution_wrong  = 0;
        embeddings = 0;
        max_collisions = 0;
        avg_collisions = 0;
        intersect_sol_truepositive = 0;
        intersect_sol_truenegative = 0;
        intersect_sol_falsepositive = 0;
        intersect_sol_falsenegative = 0;
        intersect_bit_truepositive = 0;
        intersect_bit_truenegative = 0;
        intersect_bit_falsepositive = 0;
        intersect_bit_falsenegative = 0;
        verify_reusage = 0;
    }
};